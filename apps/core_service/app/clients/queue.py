import json
from typing import TypeVar

from pydantic import BaseModel
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from apps.core_service.app.errors import QueueClientError, QueuePayloadError
from apps.core_service.app.schemas.queue import ExtractorTaskMessage, ParserTaskMessage

QueueMessageT = TypeVar("QueueMessageT", ParserTaskMessage, ExtractorTaskMessage)


class QueueClient:
    queue_name: str
    extractor_queue_name: str | None = None
    reextract_queue_name: str | None = None

    async def healthcheck(self) -> None:
        return None

    async def publish_parser_task(self, message: ParserTaskMessage) -> None:
        raise NotImplementedError

    async def consume_parser_task(self, *, timeout_seconds: int) -> ParserTaskMessage | None:
        raise NotImplementedError

    async def publish_extractor_task(self, message: ExtractorTaskMessage) -> None:
        raise NotImplementedError

    async def consume_extractor_task(
        self,
        *,
        timeout_seconds: int,
    ) -> ExtractorTaskMessage | None:
        raise NotImplementedError

    async def publish_reextract_task(self, message: ExtractorTaskMessage) -> None:
        raise NotImplementedError

    async def consume_reextract_task(
        self,
        *,
        timeout_seconds: int,
    ) -> ExtractorTaskMessage | None:
        raise NotImplementedError

    async def dispose(self) -> None:
        return None


class RedisQueueClient(QueueClient):
    def __init__(
        self,
        *,
        redis_url: str,
        queue_name: str,
        extractor_queue_name: str | None = None,
        reextract_queue_name: str | None = None,
    ) -> None:
        self.queue_name = queue_name
        self.extractor_queue_name = extractor_queue_name
        self.reextract_queue_name = reextract_queue_name
        self._redis = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def healthcheck(self) -> None:
        try:
            await self._redis.ping()
        except RedisError as exc:
            raise QueueClientError(
                f"Failed to connect to Redis queue '{self.queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def publish_parser_task(self, message: ParserTaskMessage) -> None:
        await self._push(queue_name=self.queue_name, message=message)

    async def consume_parser_task(self, *, timeout_seconds: int) -> ParserTaskMessage | None:
        return await self._pop(
            queue_name=self.queue_name,
            timeout_seconds=timeout_seconds,
            message_type=ParserTaskMessage,
        )

    async def publish_extractor_task(self, message: ExtractorTaskMessage) -> None:
        await self._push(queue_name=self._get_extractor_queue_name(), message=message)

    async def consume_extractor_task(
        self,
        *,
        timeout_seconds: int,
    ) -> ExtractorTaskMessage | None:
        return await self._pop(
            queue_name=self._get_extractor_queue_name(),
            timeout_seconds=timeout_seconds,
            message_type=ExtractorTaskMessage,
        )

    async def publish_reextract_task(self, message: ExtractorTaskMessage) -> None:
        await self._push(queue_name=self._get_reextract_queue_name(), message=message)

    async def consume_reextract_task(
        self,
        *,
        timeout_seconds: int,
    ) -> ExtractorTaskMessage | None:
        return await self._pop(
            queue_name=self._get_reextract_queue_name(),
            timeout_seconds=timeout_seconds,
            message_type=ExtractorTaskMessage,
        )

    async def _push(
        self,
        *,
        queue_name: str,
        message: BaseModel,
    ) -> None:
        payload = json.dumps(message.model_dump(mode="json"), ensure_ascii=True)
        try:
            await self._redis.rpush(queue_name, payload)
        except RedisError as exc:
            raise QueueClientError(
                f"Failed to publish to Redis queue '{queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def _pop(
        self,
        *,
        queue_name: str,
        timeout_seconds: int,
        message_type: type[QueueMessageT],
    ) -> QueueMessageT | None:
        try:
            result = await self._redis.blpop(queue_name, timeout=timeout_seconds)
        except RedisError as exc:
            raise QueueClientError(
                f"Failed to consume from Redis queue '{queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

        if result is None:
            return None

        _, payload = result
        try:
            return message_type.model_validate_json(payload)
        except ValidationError as exc:
            raise QueuePayloadError(
                f"Invalid payload was received from Redis queue '{queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

    def _get_extractor_queue_name(self) -> str:
        if self.extractor_queue_name is None:
            raise QueueClientError(
                "Extractor queue name is not configured.",
                reason="ExtractorQueueNameMissing",
            )
        return self.extractor_queue_name

    def _get_reextract_queue_name(self) -> str:
        if self.reextract_queue_name is None:
            raise QueueClientError(
                "Reextract queue name is not configured.",
                reason="ReextractQueueNameMissing",
            )
        return self.reextract_queue_name

    async def dispose(self) -> None:
        await self._redis.aclose()
