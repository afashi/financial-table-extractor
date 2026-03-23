import logging
from dataclasses import dataclass

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.db.models.task import Task
from apps.core_service.app.errors import AppError
from apps.core_service.app.repositories.task_repository import TaskRepository
from apps.core_service.app.utils.file_hashing import FileFingerprint, build_file_fingerprint
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
        trace_id: str,
        repository: TaskRepository | None = None,
    ) -> None:
        self._session = session
        self._id_generator = id_generator
        self._logger = logger
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
                "Created extract task.",
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
            ) from exc
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
            ) from exc

        if task is None:
            raise AppError(
                code="TASK_NOT_FOUND",
                message=f"Task {task_id} was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                task_id=task_id,
            )

        return task

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
