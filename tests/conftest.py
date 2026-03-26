from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from apps.core_service.app.clients.object_storage import (
    ObjectStorageClient,
    StoredObjectRef,
)
from apps.core_service.app.clients.queue import QueueClient
from apps.core_service.app.db.models.task import Task
from apps.core_service.app.errors import QueueClientError, QueuePayloadError, StorageClientError
from apps.core_service.app.main import create_app
from apps.core_service.app.schemas.queue import ParserTaskMessage
from apps.core_service.app.settings import Settings


@dataclass(frozen=True, slots=True)
class RecordedUpload:
    bucket: str
    object_key: str
    data: bytes
    content_type: str | None


class FakeObjectStorageClient(ObjectStorageClient):
    def __init__(self, *, bucket_name: str = "test-bucket") -> None:
        self.bucket_name = bucket_name
        self.uploads: list[RecordedUpload] = []
        self.deleted_object_keys: list[str] = []
        self.upload_failures_remaining = 0
        self.download_failures_remaining = 0

    async def upload_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str | None,
        bucket: str | None = None,
    ) -> StoredObjectRef:
        target_bucket = bucket or self.bucket_name
        if self.upload_failures_remaining > 0:
            self.upload_failures_remaining -= 1
            raise StorageClientError(
                f"Failed to upload object '{object_key}'.",
                reason="FakeUploadFailure",
            )

        self.uploads.append(
            RecordedUpload(
                bucket=target_bucket,
                object_key=object_key,
                data=data,
                content_type=content_type,
            )
        )
        return StoredObjectRef(bucket=target_bucket, object_key=object_key)

    async def download_bytes(
        self,
        *,
        object_key: str,
        bucket: str | None = None,
    ) -> bytes:
        if self.download_failures_remaining > 0:
            self.download_failures_remaining -= 1
            raise StorageClientError(
                f"Failed to download object '{object_key}'.",
                reason="FakeDownloadFailure",
            )

        for upload in reversed(self.uploads):
            if upload.object_key == object_key and upload.bucket == (bucket or self.bucket_name):
                return upload.data

        raise StorageClientError(
            f"Object '{object_key}' was not found.",
            reason="FakeObjectMissing",
        )

    async def delete_object(self, *, object_key: str, bucket: str | None = None) -> None:
        self.deleted_object_keys.append(object_key)


class FakeQueueClient(QueueClient):
    def __init__(self, *, queue_name: str = "parser_queue") -> None:
        self.queue_name = queue_name
        self.messages: list[ParserTaskMessage] = []
        self.invalid_payloads: list[str] = []
        self.publish_failures_remaining = 0
        self.consume_failures_remaining = 0

    async def publish_parser_task(self, message: ParserTaskMessage) -> None:
        if self.publish_failures_remaining > 0:
            self.publish_failures_remaining -= 1
            raise QueueClientError(
                f"Failed to publish queue message to '{self.queue_name}'.",
                reason="FakePublishFailure",
            )

        self.messages.append(message)

    async def consume_parser_task(self, *, timeout_seconds: int) -> ParserTaskMessage | None:
        if self.consume_failures_remaining > 0:
            self.consume_failures_remaining -= 1
            raise QueueClientError(
                f"Failed to consume queue message from '{self.queue_name}'.",
                reason="FakeConsumeFailure",
            )

        if self.invalid_payloads:
            payload = self.invalid_payloads.pop(0)
            try:
                return ParserTaskMessage.model_validate_json(payload)
            except ValidationError as exc:
                raise QueuePayloadError(
                    f"Invalid payload was received from '{self.queue_name}'.",
                    reason=exc.__class__.__name__,
                ) from exc

        if not self.messages:
            return None

        return self.messages.pop(0)


class FakeAsyncSession:
    async def __aenter__(self) -> "FakeAsyncSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def refresh(self, instance: object) -> None:
        return None

    async def flush(self) -> None:
        return None


class FakeDatabaseClient:
    def session_factory(self) -> FakeAsyncSession:
        return FakeAsyncSession()

    async def healthcheck(self) -> None:
        return None

    async def dispose(self) -> None:
        return None


class FakeTaskRepository:
    def __init__(self) -> None:
        self._tasks_by_id: dict[int, Task] = {}
        self._task_ids_by_fingerprint: dict[tuple[str, int, str], int] = {}

    async def get_by_id(self, session, task_id: int) -> Task | None:
        del session
        return self._tasks_by_id.get(task_id)

    async def get_by_fingerprint(
        self,
        session,
        *,
        file_hash: str,
        file_size: int,
        doc_type: str,
    ) -> Task | None:
        del session
        task_id = self._task_ids_by_fingerprint.get(
            (file_hash, file_size, _enum_value(doc_type)),
        )
        if task_id is None:
            return None
        return self._tasks_by_id.get(task_id)

    async def create(self, session, task: Task) -> Task:
        del session
        now = _utc_now()
        task.create_time = now
        task.update_time = now
        self._tasks_by_id[task.id] = task
        self._task_ids_by_fingerprint[
            (task.file_hash, task.file_size, _enum_value(task.doc_type))
        ] = task.id
        return task

    async def touch(self, session, task: Task) -> Task:
        del session
        task.update_time = _utc_now()
        return task

    async def set_status(
        self,
        session,
        task: Task,
        *,
        status: str,
        remark: str | None,
    ) -> Task:
        del session
        task.status = _enum_value(status)
        task.remark = remark
        task.update_time = _utc_now()
        return task


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _enum_value(value: str) -> str:
    return value.value if hasattr(value, "value") else value


@pytest.fixture
async def test_app() -> AsyncIterator:
    database_client = FakeDatabaseClient()
    object_storage_client = FakeObjectStorageClient()
    queue_client = FakeQueueClient()
    task_repository = FakeTaskRepository()
    settings = Settings(
        database_url="sqlite+aiosqlite:///unused.db",
        task_id_node_id=7,
        minio_bucket=object_storage_client.bucket_name,
        parser_queue_name=queue_client.queue_name,
    )
    app = create_app(
        settings,
        database_client=database_client,
        object_storage_client=object_storage_client,
        queue_client=queue_client,
    )
    app.state.task_repository = task_repository

    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def async_client(test_app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
