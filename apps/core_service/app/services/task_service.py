import logging
from dataclasses import dataclass

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.clients.object_storage import ObjectStorageClient
from apps.core_service.app.clients.queue import QueueClient
from apps.core_service.app.db.models.task import Task
from apps.core_service.app.errors import AppError, QueueClientError, StorageClientError
from apps.core_service.app.repositories.task_repository import TaskRepository
from apps.core_service.app.schemas.queue import ParserTaskMessage
from apps.core_service.app.utils.file_hashing import FileFingerprint, build_file_fingerprint
from apps.core_service.app.utils.object_storage import build_source_object_key
from apps.shared.enums.doc_type import DocumentType
from apps.shared.enums.task_status import TaskStatus
from apps.shared.utils.snowflake import SnowflakeIdGenerator


@dataclass(slots=True)
class TaskSubmissionResult:
    task: Task
    deduplicated: bool


class TaskService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        id_generator: SnowflakeIdGenerator,
        logger: logging.Logger,
        object_storage_client: ObjectStorageClient,
        queue_client: QueueClient,
        trace_id: str,
        repository: TaskRepository | None = None,
    ) -> None:
        self._session = session
        self._id_generator = id_generator
        self._logger = logger
        self._object_storage_client = object_storage_client
        self._queue_client = queue_client
        self._trace_id = trace_id
        self._repository = repository or TaskRepository()

    async def create_extract_task(
        self,
        *,
        doc_type: DocumentType,
        upload: UploadFile,
    ) -> TaskSubmissionResult:
        try:
            if not upload.filename:
                raise AppError(
                    code="INVALID_FILE_UPLOAD",
                    message="Uploaded file must include a filename.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            file_bytes = await upload.read()
            fingerprint = build_file_fingerprint(upload.filename, file_bytes)

            existing = await self._repository.get_by_fingerprint(
                self._session,
                file_hash=fingerprint.file_hash,
                file_size=fingerprint.file_size,
                doc_type=doc_type,
            )
            if existing is not None:
                return await self._handle_existing_task(
                    existing=existing,
                    file_bytes=file_bytes,
                    content_type=upload.content_type,
                )

            task = Task(
                id=self._id_generator.next_id(),
                doc_type=doc_type,
                file_name=fingerprint.file_name,
                file_hash=fingerprint.file_hash,
                file_size=fingerprint.file_size,
                status=TaskStatus.QUEUED,
            )
            task = await self._repository.create(self._session, task)
            await self._session.commit()
            await self._session.refresh(task)

            self._logger.info(
                "Created extract task record.",
                extra={
                    "service": "core_service",
                    "phase": "task_submission",
                    "event": "task_created",
                    "task_id": task.id,
                    "doc_type": task.doc_type,
                    "file_size": task.file_size,
                    "trace_id": self._trace_id,
                },
            )

            await self._dispatch_task(
                task,
                file_bytes=file_bytes,
                content_type=upload.content_type,
            )
            return TaskSubmissionResult(task=task, deduplicated=False)
        except IntegrityError:
            await self._session.rollback()
            return await self._recover_from_duplicate(doc_type=doc_type, fingerprint=fingerprint)
        except AppError:
            await self._session.rollback()
            raise
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise AppError(
                code="DATABASE_UNAVAILABLE",
                message="Database operation failed while creating the task.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                retryable=True,
                details={"reason": exc.__class__.__name__},
            )
        finally:
            await upload.close()

    async def get_task(self, task_id: int) -> Task:
        try:
            task = await self._repository.get_by_id(self._session, task_id)
        except SQLAlchemyError as exc:
            raise AppError(
                code="DATABASE_UNAVAILABLE",
                message="Database operation failed while retrieving the task.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                retryable=True,
                details={"reason": exc.__class__.__name__},
                task_id=task_id,
            )

        if task is None:
            raise AppError(
                code="TASK_NOT_FOUND",
                message=f"Task {task_id} was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                task_id=task_id,
            )

        return task

    async def _handle_existing_task(
        self,
        *,
        existing: Task,
        file_bytes: bytes,
        content_type: str | None,
    ) -> TaskSubmissionResult:
        existing_status = TaskStatus(existing.status)
        if existing_status != TaskStatus.FAILED:
            existing = await self._repository.touch(self._session, existing)
            await self._session.commit()
            self._logger.info(
                "Reused existing task for duplicate upload.",
                extra={
                    "service": "core_service",
                    "phase": "task_submission",
                    "event": "task_deduplicated",
                    "task_id": existing.id,
                    "doc_type": existing.doc_type,
                    "trace_id": self._trace_id,
                },
            )
            return TaskSubmissionResult(task=existing, deduplicated=True)

        await self._dispatch_task(
            existing,
            file_bytes=file_bytes,
            content_type=content_type,
        )

        try:
            existing = await self._repository.set_status(
                self._session,
                existing,
                status=TaskStatus.QUEUED,
                remark=None,
            )
            await self._session.commit()
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise AppError(
                code="DATABASE_UNAVAILABLE",
                message="Database operation failed while re-queueing the task.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                retryable=True,
                details={"reason": exc.__class__.__name__},
                task_id=existing.id,
            ) from exc

        self._logger.info(
            "Re-dispatched previously failed task.",
            extra={
                "service": "core_service",
                "phase": "task_submission",
                "event": "task_redispatched",
                "task_id": existing.id,
                "doc_type": existing.doc_type,
                "trace_id": self._trace_id,
            },
        )
        return TaskSubmissionResult(task=existing, deduplicated=True)

    async def _dispatch_task(
        self,
        task: Task,
        *,
        file_bytes: bytes,
        content_type: str | None,
    ) -> None:
        object_key = build_source_object_key(task.id, task.file_name)

        try:
            stored_object = await self._object_storage_client.upload_bytes(
                object_key=object_key,
                data=file_bytes,
                content_type=content_type,
            )
        except StorageClientError as exc:
            app_error = AppError(
                code="OBJECT_STORAGE_UNAVAILABLE",
                message="Failed to store the uploaded PDF in object storage.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                retryable=True,
                details={
                    "reason": exc.reason,
                    "bucket": self._object_storage_client.bucket_name,
                    "object_key": object_key,
                },
                task_id=task.id,
            )
            await self._persist_dispatch_failure(
                task,
                remark="Failed to store source PDF in object storage.",
                boundary_code=app_error.code,
            )
            raise app_error from exc

        message = ParserTaskMessage(
            task_id=str(task.id),
            doc_type=DocumentType(task.doc_type),
            file_name=task.file_name,
            file_hash=task.file_hash,
            file_size=task.file_size,
            bucket=stored_object.bucket,
            source_object_key=stored_object.object_key,
        )

        try:
            await self._queue_client.publish_parser_task(message)
        except QueueClientError as exc:
            app_error = AppError(
                code="QUEUE_UNAVAILABLE",
                message="Failed to publish the parser task message.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                retryable=True,
                details={
                    "reason": exc.reason,
                    "queue_name": self._queue_client.queue_name,
                    "bucket": stored_object.bucket,
                    "object_key": stored_object.object_key,
                },
                task_id=task.id,
            )
            await self._persist_dispatch_failure(
                task,
                remark="Failed to publish parser task message.",
                boundary_code=app_error.code,
            )
            raise app_error from exc

        self._logger.info(
            "Dispatched parser task.",
            extra={
                "service": "core_service",
                "phase": "task_submission",
                "event": "task_dispatched",
                "task_id": task.id,
                "doc_type": task.doc_type,
                "trace_id": self._trace_id,
                "queue_name": self._queue_client.queue_name,
                "object_key": stored_object.object_key,
            },
        )

    async def _persist_dispatch_failure(
        self,
        task: Task,
        *,
        remark: str,
        boundary_code: str,
    ) -> None:
        try:
            await self._repository.set_status(
                self._session,
                task,
                status=TaskStatus.FAILED,
                remark=remark,
            )
            await self._session.commit()
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise AppError(
                code="DATABASE_UNAVAILABLE",
                message="Task dispatch failed and the failure state could not be persisted.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                retryable=True,
                details={
                    "reason": exc.__class__.__name__,
                    "dispatch_error_code": boundary_code,
                },
                task_id=task.id,
            ) from exc

        self._logger.error(
            "Task dispatch failed.",
            extra={
                "service": "core_service",
                "phase": "task_submission",
                "event": "task_dispatch_failed",
                "task_id": task.id,
                "doc_type": task.doc_type,
                "trace_id": self._trace_id,
                "code": boundary_code,
            },
        )

    async def _recover_from_duplicate(
        self,
        *,
        doc_type: DocumentType,
        fingerprint: FileFingerprint,
    ) -> TaskSubmissionResult:
        existing = await self._repository.get_by_fingerprint(
            self._session,
            file_hash=fingerprint.file_hash,
            file_size=fingerprint.file_size,
            doc_type=doc_type,
        )
        if existing is None:
            raise AppError(
                code="DATABASE_UNAVAILABLE",
                message="Task creation failed and could not recover duplicate state.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                retryable=True,
            )

        existing = await self._repository.touch(self._session, existing)
        await self._session.commit()
        return TaskSubmissionResult(task=existing, deduplicated=True)
