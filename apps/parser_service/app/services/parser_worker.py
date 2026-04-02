import logging
from collections.abc import Callable
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.core_service.app.clients.object_storage import ObjectStorageClient
from apps.core_service.app.clients.queue import QueueClient
from apps.core_service.app.db.models.task import Task
from apps.core_service.app.errors import QueueClientError, QueuePayloadError, StorageClientError
from apps.core_service.app.repositories.task_repository import TaskRepository
from apps.core_service.app.schemas.queue import ExtractorTaskMessage, ParserTaskMessage
from apps.core_service.app.utils.object_storage import build_content_list_object_key
from apps.parser_service.app.services.parser_engine import ParserEngine, ParserEngineError
from apps.shared.enums.task_status import TaskStatus


class ParserWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        object_storage_client: ObjectStorageClient,
        queue_client: QueueClient,
        parser_engine: ParserEngine,
        logger: logging.Logger,
        repository: TaskRepository | None = None,
        trace_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._object_storage_client = object_storage_client
        self._queue_client = queue_client
        self._parser_engine = parser_engine
        self._logger = logger
        self._repository = repository or TaskRepository()
        self._trace_id_factory = trace_id_factory or (lambda: uuid4().hex)

    async def process_next_message(self, *, timeout_seconds: int) -> bool:
        try:
            message = await self._queue_client.consume_parser_task(timeout_seconds=timeout_seconds)
        except QueuePayloadError as exc:
            self._logger.error(
                "Discarded invalid parser queue payload.",
                extra={
                    "service": "parser_service",
                    "phase": "queue_consume",
                    "event": "parse_failed",
                    "task_id": None,
                    "trace_id": self._trace_id_factory(),
                    "queue_name": self._queue_client.queue_name,
                    "code": "QUEUE_PAYLOAD_INVALID",
                    "reason": exc.reason,
                },
            )
            return True
        except QueueClientError:
            raise

        if message is None:
            return False

        return await self._process_message(message)

    async def _process_message(self, message: ParserTaskMessage) -> bool:
        trace_id = self._trace_id_factory()
        task = await self._mark_parsing(message, trace_id=trace_id)
        if task is None:
            return True

        self._logger.info(
            "Parser task started.",
            extra={
                "service": "parser_service",
                "phase": "parse_start",
                "event": "parse_started",
                "task_id": task.id,
                "doc_type": task.doc_type,
                "trace_id": trace_id,
                "queue_name": self._queue_client.queue_name,
                "object_key": message.source_object_key,
            },
        )

        try:
            source_pdf = await self._object_storage_client.download_bytes(
                bucket=message.bucket,
                object_key=message.source_object_key,
            )
        except StorageClientError as exc:
            await self._mark_failed(
                task.id,
                remark="Failed to load source PDF from object storage.",
                trace_id=trace_id,
                code="OBJECT_STORAGE_UNAVAILABLE",
                reason=exc.reason,
            )
            return True

        try:
            artifact_bytes = await self._parser_engine.parse(
                source_pdf=source_pdf,
                message=message,
            )
        except ParserEngineError as exc:
            await self._mark_failed(
                task.id,
                remark="Failed to parse source PDF.",
                trace_id=trace_id,
                code="PARSE_FAILED",
                reason=exc.reason,
            )
            return True

        artifact_key = build_content_list_object_key(task.id)
        try:
            await self._object_storage_client.upload_bytes(
                bucket=message.bucket,
                object_key=artifact_key,
                data=artifact_bytes,
                content_type="application/json",
            )
        except StorageClientError as exc:
            await self._mark_failed(
                task.id,
                remark="Failed to persist parser artifact to object storage.",
                trace_id=trace_id,
                code="OBJECT_STORAGE_UNAVAILABLE",
                reason=exc.reason,
            )
            return True

        extractor_message = ExtractorTaskMessage(
            task_id=message.task_id,
            doc_type=message.doc_type,
            bucket=message.bucket,
            content_list_object_key=artifact_key,
        )
        try:
            await self._queue_client.publish_extractor_task(extractor_message)
        except QueueClientError as exc:
            await self._mark_failed(
                task.id,
                remark="Failed to publish extractor task message.",
                trace_id=trace_id,
                code="QUEUE_UNAVAILABLE",
                reason=exc.reason,
                queue_name=self._queue_client.extractor_queue_name,
            )
            return True

        await self._mark_parsed(task.id, trace_id=trace_id, artifact_key=artifact_key)
        return True

    async def _mark_parsing(self, message: ParserTaskMessage, *, trace_id: str) -> Task | None:
        async with self._session_factory() as session:
            try:
                task_id = int(message.task_id)
                task = await self._repository.get_by_id(session, task_id)
                if task is None:
                    self._logger.warning(
                        "Parser queue message referenced a missing task.",
                        extra={
                            "service": "parser_service",
                            "phase": "queue_consume",
                            "event": "task_missing",
                            "task_id": task_id,
                            "trace_id": trace_id,
                            "queue_name": self._queue_client.queue_name,
                            "object_key": message.source_object_key,
                        },
                    )
                    return None

                task = await self._repository.set_status(
                    session,
                    task,
                    status=TaskStatus.PARSING,
                    remark=None,
                )
                await session.commit()
                return task
            except SQLAlchemyError as exc:
                await session.rollback()
                self._logger.error(
                    "Failed to persist parser start state.",
                    extra={
                        "service": "parser_service",
                        "phase": "parse_start",
                        "event": "parse_failed",
                        "task_id": message.task_id,
                        "trace_id": trace_id,
                        "code": "DATABASE_UNAVAILABLE",
                        "reason": exc.__class__.__name__,
                    },
                )
                return None

    async def _mark_parsed(self, task_id: int, *, trace_id: str, artifact_key: str) -> None:
        async with self._session_factory() as session:
            try:
                task = await self._repository.get_by_id(session, task_id)
                if task is None:
                    return
                await self._repository.set_status(
                    session,
                    task,
                    status=TaskStatus.PARSED,
                    remark=None,
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                self._logger.error(
                    "Failed to persist parser completion state.",
                    extra={
                        "service": "parser_service",
                        "phase": "parse_complete",
                        "event": "parse_failed",
                        "task_id": task_id,
                        "trace_id": trace_id,
                        "code": "DATABASE_UNAVAILABLE",
                        "reason": exc.__class__.__name__,
                    },
                )
                return

        self._logger.info(
            "Parser task completed.",
            extra={
                "service": "parser_service",
                "phase": "parse_complete",
                "event": "parse_completed",
                "task_id": task_id,
                "trace_id": trace_id,
                "queue_name": self._queue_client.queue_name,
                "object_key": artifact_key,
            },
        )

    async def _mark_failed(
        self,
        task_id: int,
        *,
        remark: str,
        trace_id: str,
        code: str,
        reason: str,
        queue_name: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            try:
                task = await self._repository.get_by_id(session, task_id)
                if task is not None:
                    await self._repository.set_status(
                        session,
                        task,
                        status=TaskStatus.FAILED,
                        remark=remark,
                    )
                    await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                self._logger.error(
                    "Failed to persist parser failure state.",
                    extra={
                        "service": "parser_service",
                        "phase": "parse_failed",
                        "event": "parse_failed",
                        "task_id": task_id,
                        "trace_id": trace_id,
                        "code": "DATABASE_UNAVAILABLE",
                        "reason": exc.__class__.__name__,
                    },
                )
                return

        self._logger.error(
            "Parser task failed.",
            extra={
                "service": "parser_service",
                "phase": "parse_failed",
                "event": "parse_failed",
                "task_id": task_id,
                "trace_id": trace_id,
                "queue_name": queue_name or self._queue_client.queue_name,
                "code": code,
                "reason": reason,
            },
        )
