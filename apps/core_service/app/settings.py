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
        "postgresql+asyncpg://postgres:postgres@localhost:55432/financial_table_extractor"
    )
    redis_url: str = "redis://localhost:6380/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "financial-table-extractor"
    log_level: str = "INFO"
    task_id_node_id: int = Field(default=1, ge=0, le=1023)
    task_id_epoch_ms: int = Field(default=1735689600000, ge=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
