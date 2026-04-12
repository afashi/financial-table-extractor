import asyncio
import logging

from apps.core_service.app.clients.llm_fallback import (
    DisabledLLMFallbackClient,
    HttpLLMFallbackClient,
)
from apps.core_service.app.clients.database import DatabaseClient
from apps.core_service.app.clients.object_storage import MinioObjectStorageClient
from apps.core_service.app.clients.queue import RedisQueueClient
from apps.core_service.app.logging_config import configure_logging
from apps.core_service.app.repositories.extracted_result_repository import (
    ExtractedResultRepository,
)
from apps.core_service.app.repositories.table_extraction_rule_repository import (
    TableExtractionRuleRepository,
)
from apps.core_service.app.repositories.task_repository import TaskRepository
from apps.core_service.app.services.extractor_worker import ExtractorWorker
from apps.core_service.app.settings import Settings, get_settings
from apps.shared.utils.snowflake import SnowflakeIdGenerator


async def run(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    logger = logging.getLogger(f"{app_settings.app_name}-extractor")

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
        extractor_queue_name=app_settings.extractor_queue_name,
    )
    llm_fallback_client = (
        HttpLLMFallbackClient(
            endpoint=app_settings.llm_fallback_url,
            model_name=app_settings.llm_fallback_model,
            api_key=app_settings.llm_fallback_api_key,
            timeout_seconds=app_settings.llm_fallback_timeout_seconds,
        )
        if app_settings.llm_fallback_enabled
        else DisabledLLMFallbackClient()
    )
    worker = ExtractorWorker(
        session_factory=database_client.session_factory,
        object_storage_client=object_storage_client,
        queue_client=queue_client,
        logger=logger,
        task_repository=TaskRepository(),
        rule_repository=TableExtractionRuleRepository(),
        result_repository=ExtractedResultRepository(),
        id_generator=SnowflakeIdGenerator(
            worker_id=app_settings.task_id_node_id,
            epoch_ms=app_settings.task_id_epoch_ms,
        ),
        llm_fallback_client=llm_fallback_client,
    )

    await database_client.healthcheck()
    await object_storage_client.healthcheck()
    await queue_client.healthcheck()

    try:
        while True:
            await worker.process_next_message(timeout_seconds=5)
    finally:
        await llm_fallback_client.dispose()
        await queue_client.dispose()
        await object_storage_client.dispose()
        await database_client.dispose()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return None
