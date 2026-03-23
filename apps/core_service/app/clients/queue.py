import json

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from apps.core_service.app.errors import QueueClientError, QueuePayloadError
from apps.core_service.app.schemas.queue import ParserTaskMessage


class QueueClient:
    queue_name: str

    async def healthcheck(self) -> None:
        return None

    async def publish_parser_task(self, message: ParserTaskMessage) -> None:
        raise NotImplementedError

    async def consume_parser_task(self, *, timeout_seconds: int) -> ParserTaskMessage | None:
        raise NotImplementedError

    async def dispose(self) -> None:
        return None


class RedisQueueClient(QueueClient):
    def __init__(self, *, redis_url: str, queue_name: str) -> None:
        self.queue_name = queue_name
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
        payload = json.dumps(message.model_dump(mode="json"), ensure_ascii=True)
        try:
            await self._redis.rpush(self.queue_name, payload)
        except RedisError as exc:
            raise QueueClientError(
                f"Failed to publish to Redis queue '{self.queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def consume_parser_task(self, *, timeout_seconds: int) -> ParserTaskMessage | None:
        try:
            result = await self._redis.blpop(self.queue_name, timeout=timeout_seconds)
        except RedisError as exc:
            raise QueueClientError(
                f"Failed to consume from Redis queue '{self.queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

        if result is None:
            return None

        _, payload = result
        try:
            return ParserTaskMessage.model_validate_json(payload)
        except ValidationError as exc:
            raise QueuePayloadError(
                f"Invalid payload was received from Redis queue '{self.queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def dispose(self) -> None:
        await self._redis.aclose()
