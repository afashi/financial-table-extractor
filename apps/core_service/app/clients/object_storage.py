import asyncio
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlparse

from minio import Minio

from apps.core_service.app.errors import StorageClientError


@dataclass(frozen=True, slots=True)
class StoredObjectRef:
    bucket: str
    object_key: str


class ObjectStorageClient:
    bucket_name: str

    async def healthcheck(self) -> None:
        return None

    async def upload_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str | None,
        bucket: str | None = None,
    ) -> StoredObjectRef:
        raise NotImplementedError

    async def download_bytes(
        self,
        *,
        object_key: str,
        bucket: str | None = None,
    ) -> bytes:
        raise NotImplementedError

    async def delete_object(self, *, object_key: str, bucket: str | None = None) -> None:
        return None

    async def dispose(self) -> None:
        return None


class MinioObjectStorageClient(ObjectStorageClient):
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
    ) -> None:
        parsed_endpoint, secure = _parse_minio_endpoint(endpoint)
        self.bucket_name = bucket_name
        self._client = Minio(
            parsed_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket_ready = False
        self._bucket_lock = asyncio.Lock()

    async def healthcheck(self) -> None:
        await self._ensure_bucket()

    async def upload_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str | None,
        bucket: str | None = None,
    ) -> StoredObjectRef:
        await self._ensure_bucket()
        payload = BytesIO(data)
        target_bucket = bucket or self.bucket_name

        try:
            await asyncio.to_thread(
                self._client.put_object,
                target_bucket,
                object_key,
                payload,
                len(data),
                content_type=content_type or "application/octet-stream",
            )
        except Exception as exc:
            raise StorageClientError(
                f"Failed to upload object '{object_key}' to bucket '{target_bucket}'.",
                reason=exc.__class__.__name__,
            ) from exc

        return StoredObjectRef(bucket=target_bucket, object_key=object_key)

    async def download_bytes(
        self,
        *,
        object_key: str,
        bucket: str | None = None,
    ) -> bytes:
        await self._ensure_bucket()
        target_bucket = bucket or self.bucket_name

        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                target_bucket,
                object_key,
            )
            try:
                return await asyncio.to_thread(response.read)
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            raise StorageClientError(
                f"Failed to download object '{object_key}' from bucket '{target_bucket}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def delete_object(self, *, object_key: str, bucket: str | None = None) -> None:
        target_bucket = bucket or self.bucket_name
        try:
            await asyncio.to_thread(
                self._client.remove_object,
                target_bucket,
                object_key,
            )
        except Exception as exc:
            raise StorageClientError(
                f"Failed to delete object '{object_key}' from bucket '{target_bucket}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return

        async with self._bucket_lock:
            if self._bucket_ready:
                return

            try:
                exists = await asyncio.to_thread(
                    self._client.bucket_exists,
                    self.bucket_name,
                )
                if not exists:
                    await asyncio.to_thread(self._client.make_bucket, self.bucket_name)
            except Exception as exc:
                raise StorageClientError(
                    f"Failed to prepare bucket '{self.bucket_name}'.",
                    reason=exc.__class__.__name__,
                ) from exc

            self._bucket_ready = True


def _parse_minio_endpoint(endpoint: str) -> tuple[str, bool]:
    normalized = endpoint if "://" in endpoint else f"http://{endpoint}"
    parsed = urlparse(normalized)
    host = parsed.netloc or parsed.path
    if not host:
        raise ValueError("minio endpoint must include a hostname.")
    return host.rstrip("/"), parsed.scheme == "https"
