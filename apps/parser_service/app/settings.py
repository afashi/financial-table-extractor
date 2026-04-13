from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "financial-table-extractor-parser-service"
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
    parser_poll_timeout_seconds: int = Field(default=5, ge=0, le=300)
    parser_backend: Literal["skeleton", "mineru"] = "skeleton"
    parser_timeout_seconds: int = Field(default=180, ge=1, le=3600)
    parser_temp_dir: str | None = None
    mineru_backend: Literal["pipeline"] | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
