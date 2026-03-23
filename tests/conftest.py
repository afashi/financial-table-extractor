from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from apps.core_service.app.clients.object_storage import (
    ObjectStorageClient,
    StoredObjectRef,
)
from apps.core_service.app.clients.queue import QueueClient
from apps.core_service.app.db.base import Base
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


@pytest.fixture
async def test_app(tmp_path) -> AsyncIterator:
    database_path = tmp_path / "test.db"
    object_storage_client = FakeObjectStorageClient()
    queue_client = FakeQueueClient()
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database_path.as_posix()}",
        task_id_node_id=7,
        minio_bucket=object_storage_client.bucket_name,
        parser_queue_name=queue_client.queue_name,
    )
    app = create_app(
        settings,
        object_storage_client=object_storage_client,
        queue_client=queue_client,
    )

    async with app.router.lifespan_context(app):
        async with app.state.database_client.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield app


@pytest.fixture
async def async_client(test_app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
