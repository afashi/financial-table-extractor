import asyncio
import logging

from apps.core_service.app.clients.database import DatabaseClient
from apps.core_service.app.clients.object_storage import MinioObjectStorageClient
from apps.core_service.app.clients.queue import RedisQueueClient
from apps.core_service.app.errors import QueueClientError
from apps.core_service.app.logging_config import configure_logging
from apps.parser_service.app.services.parser_engine import SkeletonParserEngine
from apps.parser_service.app.services.parser_worker import ParserWorker
from apps.parser_service.app.settings import Settings, get_settings


async def run(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    logger = logging.getLogger(app_settings.app_name)

    database_client = DatabaseClient(app_settings.database_url)
    object_storage_client = MinioObjectStorageClient(
        endpoint=app_settings.minio_endpoint,
        access_key=app_settings.minio_root_user,
        secret_key=app_settings.minio_root_password,
        bucket_name=app_settings.minio_bucket,
    )
    queue_client = RedisQueueClient(
        redis_url=app_settings.redis_url,
        queue_name=app_settings.parser_queue_name,
    )
    worker = ParserWorker(
        session_factory=database_client.session_factory,
        object_storage_client=object_storage_client,
        queue_client=queue_client,
        parser_engine=SkeletonParserEngine(),
        logger=logger,
    )

    await database_client.healthcheck()
    await object_storage_client.healthcheck()
    await queue_client.healthcheck()

    logger.info(
        "Parser service started.",
        extra={
            "service": "parser_service",
            "phase": "startup",
            "event": "service_started",
            "task_id": None,
            "trace_id": "parser-service-startup",
            "queue_name": queue_client.queue_name,
        },
    )

    try:
        while True:
            try:
                await worker.process_next_message(
                    timeout_seconds=app_settings.parser_poll_timeout_seconds,
                )
            except QueueClientError as exc:
                logger.error(
                    "Parser service failed to consume from queue.",
                    extra={
                        "service": "parser_service",
                        "phase": "queue_consume",
                        "event": "parse_failed",
                        "task_id": None,
                        "trace_id": "parser-service-consume-error",
                        "queue_name": queue_client.queue_name,
                        "code": "QUEUE_UNAVAILABLE",
                        "reason": exc.reason,
                    },
                )
                await asyncio.sleep(1)
    finally:
        await queue_client.dispose()
        await object_storage_client.dispose()
        await database_client.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
