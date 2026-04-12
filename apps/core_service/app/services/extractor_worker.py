import json
import logging
from collections.abc import Callable
from decimal import Decimal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.core_service.app.clients.llm_fallback import (
    DisabledLLMFallbackClient,
    LLMFallbackClient,
)
from apps.core_service.app.clients.object_storage import ObjectStorageClient
from apps.core_service.app.clients.queue import QueueClient
from apps.core_service.app.errors import (
    LLMFallbackClientError,
    QueueClientError,
    QueuePayloadError,
    StorageClientError,
)
from apps.core_service.app.repositories.extracted_result_repository import (
    ExtractedResultRepository,
)
from apps.core_service.app.repositories.table_extraction_rule_repository import (
    TableExtractionRuleRepository,
)
from apps.core_service.app.repositories.task_repository import TaskRepository
from apps.core_service.app.schemas.artifact import load_content_list
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.routing import RouteDecision
from apps.core_service.app.services.fast_track_extractor import FastTrackExtractor
from apps.core_service.app.services.logical_table_builder import LogicalTableBuilder
from apps.core_service.app.services.table_router import TableRouter
from apps.core_service.app.utils.object_storage import build_logical_tables_object_key
from apps.shared.enums.task_status import TaskStatus
from apps.shared.utils.snowflake import SnowflakeIdGenerator


class ExtractorWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        object_storage_client: ObjectStorageClient,
        queue_client: QueueClient,
        logger: logging.Logger,
        task_repository: TaskRepository,
        rule_repository: TableExtractionRuleRepository,
        result_repository: ExtractedResultRepository,
        id_generator: SnowflakeIdGenerator,
        logical_table_builder: LogicalTableBuilder | None = None,
        table_router: TableRouter | None = None,
        fast_track_extractor: FastTrackExtractor | None = None,
        llm_fallback_client: LLMFallbackClient | None = None,
        trace_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._object_storage_client = object_storage_client
        self._queue_client = queue_client
        self._logger = logger
        self._task_repository = task_repository
        self._rule_repository = rule_repository
        self._result_repository = result_repository
        self._id_generator = id_generator
        self._trace_id_factory = trace_id_factory or (lambda: uuid4().hex)
        self._logical_table_builder = logical_table_builder or LogicalTableBuilder()
        self._table_router = table_router or TableRouter()
        self._fast_track_extractor = fast_track_extractor or FastTrackExtractor()
        self._llm_fallback_client = llm_fallback_client or DisabledLLMFallbackClient()

    async def process_next_message(self, *, timeout_seconds: int) -> bool:
        try:
            message = await self._queue_client.consume_extractor_task(
                timeout_seconds=timeout_seconds
            )
        except QueuePayloadError as exc:
            self._logger.error(
                "Discarded invalid extractor queue payload.",
                extra={
                    "service": "core_service",
                    "phase": "extract_queue_consume",
                    "event": "extract_failed",
                    "task_id": None,
                    "trace_id": self._trace_id_factory(),
                    "queue_name": self._queue_client.extractor_queue_name,
                    "code": "QUEUE_PAYLOAD_INVALID",
                    "reason": exc.reason,
                },
            )
            return True
        except QueueClientError:
            raise

        if message is None:
            return False

        trace_id = self._trace_id_factory()
        try:
            artifact_bytes = await self._object_storage_client.download_bytes(
                bucket=message.bucket,
                object_key=message.content_list_object_key,
            )
        except StorageClientError as exc:
            await self._mark_failed(
                int(message.task_id),
                remark="Failed to load parser artifact from object storage.",
                trace_id=trace_id,
                code="OBJECT_STORAGE_UNAVAILABLE",
                reason=exc.reason,
                bucket=message.bucket,
                object_key=message.content_list_object_key,
            )
            return True
        try:
            content_blocks = load_content_list(artifact_bytes)
        except ValidationError as exc:
            await self._mark_failed(
                int(message.task_id),
                remark="Parser artifact does not match the canonical content_list contract.",
                trace_id=trace_id,
                code="ARTIFACT_INVALID",
                reason=str(exc),
                bucket=message.bucket,
                object_key=message.content_list_object_key,
            )
            return True

        async with self._session_factory() as session:
            try:
                task = await self._task_repository.get_by_id(session, int(message.task_id))
                if task is None:
                    self._logger.warning(
                        "Extractor task referenced a missing task record.",
                        extra={
                            "service": "core_service",
                            "phase": "extract_prepare",
                            "event": "extract_skipped",
                            "task_id": message.task_id,
                            "trace_id": trace_id,
                            "bucket": message.bucket,
                            "object_key": message.content_list_object_key,
                            "code": "TASK_NOT_FOUND",
                        },
                    )
                    return True
            except SQLAlchemyError as exc:
                await session.rollback()
                self._logger.error(
                    "Failed to load extractor task state.",
                    extra={
                        "service": "core_service",
                        "phase": "extract_prepare",
                        "event": "extract_failed",
                        "task_id": message.task_id,
                        "trace_id": trace_id,
                        "bucket": message.bucket,
                        "object_key": message.content_list_object_key,
                        "code": "DATABASE_UNAVAILABLE",
                        "reason": exc.__class__.__name__,
                    },
                )
                return True

        logical_tables = self._logical_table_builder.build(content_blocks)
        logical_tables_object_key = build_logical_tables_object_key(int(message.task_id))
        logical_tables_payload = json.dumps(
            [table.model_dump(mode="json") for table in logical_tables],
            ensure_ascii=True,
        ).encode("utf-8")
        try:
            await self._object_storage_client.upload_bytes(
                bucket=message.bucket,
                object_key=logical_tables_object_key,
                data=logical_tables_payload,
                content_type="application/json",
            )
        except StorageClientError as exc:
            await self._mark_failed(
                int(message.task_id),
                remark="Failed to persist logical tables artifact to object storage.",
                trace_id=trace_id,
                code="OBJECT_STORAGE_UNAVAILABLE",
                reason=exc.reason,
                bucket=message.bucket,
                object_key=logical_tables_object_key,
            )
            return True

        async with self._session_factory() as session:
            try:
                task = await self._task_repository.get_by_id(session, int(message.task_id))
                if task is None:
                    await self._cleanup_logical_tables_artifact(
                        bucket=message.bucket,
                        object_key=logical_tables_object_key,
                        task_id=message.task_id,
                        trace_id=trace_id,
                    )
                    self._logger.warning(
                        "Extractor task disappeared before result persistence.",
                        extra={
                            "service": "core_service",
                            "phase": "extract_complete",
                            "event": "extract_skipped",
                            "task_id": message.task_id,
                            "trace_id": trace_id,
                            "bucket": message.bucket,
                            "object_key": logical_tables_object_key,
                            "code": "TASK_NOT_FOUND",
                        },
                    )
                    return True

                rules = await self._rule_repository.list_active_by_doc_type(
                    session,
                    doc_type=message.doc_type,
                )
                for rule in rules:
                    decision = self._table_router.route(
                        rule=rule,
                        logical_tables=logical_tables,
                        content_blocks=content_blocks,
                    )
                    outcome = await self._build_outcome(rule=rule, decision=decision)
                    await self._result_repository.upsert_result(
                        session,
                        result_id=self._id_generator.next_id(),
                        task_id=task.id,
                        rule=rule,
                        outcome=outcome,
                    )

                await self._task_repository.set_status(
                    session,
                    task,
                    status=TaskStatus.COMPLETED,
                    remark=None if rules else "No active extraction rules configured.",
                )
                await session.commit()
            except (SQLAlchemyError, LLMFallbackClientError) as exc:
                await session.rollback()
                if isinstance(exc, LLMFallbackClientError):
                    await self._mark_failed(
                        int(message.task_id),
                        remark="Failed to call LLM fallback endpoint.",
                        trace_id=trace_id,
                        code="LLM_FALLBACK_UNAVAILABLE",
                        reason=exc.reason,
                        bucket=message.bucket,
                        object_key=logical_tables_object_key,
                    )
                    return True
                await self._cleanup_logical_tables_artifact(
                    bucket=message.bucket,
                    object_key=logical_tables_object_key,
                    task_id=message.task_id,
                    trace_id=trace_id,
                )
                self._logger.error(
                    "Failed to persist extractor result state.",
                    extra={
                        "service": "core_service",
                        "phase": "extract_complete",
                        "event": "extract_failed",
                        "task_id": message.task_id,
                        "trace_id": trace_id,
                        "bucket": message.bucket,
                        "object_key": logical_tables_object_key,
                        "code": "DATABASE_UNAVAILABLE",
                        "reason": exc.__class__.__name__,
                    },
                )
                return True

        self._logger.info(
            "Extractor task completed.",
            extra={
                "service": "core_service",
                "phase": "extract_complete",
                "event": "extract_completed",
                "task_id": message.task_id,
                "trace_id": trace_id,
                "queue_name": self._queue_client.extractor_queue_name,
                "object_key": message.content_list_object_key,
                "logical_tables_object_key": logical_tables_object_key,
                "logical_table_count": len(logical_tables),
            },
        )
        return True

    async def _build_outcome(
        self,
        *,
        rule,
        decision: RouteDecision,
    ) -> ExtractionOutcome:
        if decision.decision == "FAST_TRACK":
            return self._fast_track_extractor.extract(decision=decision)
        if decision.decision == "SLOW_TRACK":
            return await self._llm_fallback_client.extract(rule=rule, decision=decision)
        return ExtractionOutcome(
            data_status="NOT_FIND",
            extraction_route=None,
            confidence_score=Decimal("100.00"),
            needs_review="0",
            remark=decision.remark,
        )

    async def _mark_failed(
        self,
        task_id: int,
        *,
        remark: str,
        trace_id: str,
        code: str,
        reason: str,
        bucket: str | None = None,
        object_key: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            try:
                task = await self._task_repository.get_by_id(session, task_id)
                if task is not None:
                    await self._task_repository.set_status(
                        session,
                        task,
                        status=TaskStatus.FAILED,
                        remark=remark,
                    )
                    await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                self._logger.error(
                    "Failed to persist extractor failure state.",
                    extra={
                        "service": "core_service",
                        "phase": "extract_failed",
                        "event": "extract_failed",
                        "task_id": task_id,
                        "trace_id": trace_id,
                        "bucket": bucket,
                        "object_key": object_key,
                        "code": "DATABASE_UNAVAILABLE",
                        "reason": "FailedToPersistFailureState",
                    },
                )
                return

        self._logger.error(
            "Extractor task failed.",
            extra={
                "service": "core_service",
                "phase": "extract_failed",
                "event": "extract_failed",
                "task_id": task_id,
                "trace_id": trace_id,
                "bucket": bucket,
                "object_key": object_key,
                "code": code,
                "reason": reason,
            },
        )

    async def _cleanup_logical_tables_artifact(
        self,
        *,
        bucket: str,
        object_key: str,
        task_id: str,
        trace_id: str,
    ) -> None:
        try:
            await self._object_storage_client.delete_object(
                bucket=bucket,
                object_key=object_key,
            )
        except StorageClientError as exc:
            self._logger.warning(
                "Failed to clean up logical tables artifact.",
                extra={
                    "service": "core_service",
                    "phase": "extract_cleanup",
                    "event": "extract_cleanup_failed",
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "bucket": bucket,
                    "object_key": object_key,
                    "code": "OBJECT_STORAGE_UNAVAILABLE",
                    "reason": exc.reason,
                },
            )
