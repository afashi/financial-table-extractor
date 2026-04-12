from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "financial-table-extractor-core-service"
    api_v1_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:25432/financial_table_extractor"
    )
    redis_url: str = "redis://localhost:26379/0"
    parser_queue_name: str = "parser_queue"
    extractor_queue_name: str = "extractor_queue"
    minio_endpoint: str = "http://localhost:29000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "financial-table-extractor"
    log_level: str = "INFO"
    llm_fallback_enabled: bool = False
    llm_fallback_url: str = "http://127.0.0.1:18080/extract"
    llm_fallback_model: str = "fallback-default"
    llm_fallback_api_key: str | None = None
    llm_fallback_timeout_seconds: float = Field(default=30.0, gt=0)
    task_id_node_id: int = Field(default=1, ge=0, le=1023)
    task_id_epoch_ms: int = Field(default=1735689600000, ge=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
