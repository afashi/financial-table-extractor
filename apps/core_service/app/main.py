import logging
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apps.core_service.app.api.router import api_router
from apps.core_service.app.clients.database import DatabaseClient
from apps.core_service.app.clients.object_storage import (
    MinioObjectStorageClient,
    ObjectStorageClient,
)
from apps.core_service.app.clients.queue import QueueClient, RedisQueueClient
from apps.core_service.app.errors import AppError
from apps.core_service.app.logging_config import configure_logging
from apps.core_service.app.schemas.errors import ErrorResponse
from apps.core_service.app.settings import Settings, get_settings
from apps.shared.utils.snowflake import SnowflakeIdGenerator


class TraceIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        trace_id = uuid4().hex
        scope.setdefault("state", {})
        scope["state"]["trace_id"] = trace_id

        async def send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Trace-Id", trace_id)
            await send(message)

        await self._app(scope, receive, send_with_trace_id)


def create_app(
    settings: Settings | None = None,
    *,
    database_client: DatabaseClient | None = None,
    object_storage_client: ObjectStorageClient | None = None,
    queue_client: QueueClient | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    logger = logging.getLogger(app_settings.app_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db_client = database_client or DatabaseClient(app_settings.database_url)
        storage_client = object_storage_client or MinioObjectStorageClient(
            endpoint=app_settings.minio_endpoint,
            access_key=app_settings.minio_root_user,
            secret_key=app_settings.minio_root_password,
            bucket_name=app_settings.minio_bucket,
        )
        parser_queue_client = queue_client or RedisQueueClient(
            redis_url=app_settings.redis_url,
            queue_name=app_settings.parser_queue_name,
        )
        await db_client.healthcheck()
        await storage_client.healthcheck()
        await parser_queue_client.healthcheck()
        app.state.settings = app_settings
        app.state.logger = logger
        app.state.database_client = db_client
        app.state.object_storage_client = storage_client
        app.state.queue_client = parser_queue_client
        app.state.task_id_generator = SnowflakeIdGenerator(
            worker_id=app_settings.task_id_node_id,
            epoch_ms=app_settings.task_id_epoch_ms,
        )
        yield
        await parser_queue_client.dispose()
        await storage_client.dispose()
        await db_client.dispose()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.add_middleware(TraceIdMiddleware)
    app.include_router(api_router)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        payload = ErrorResponse(
            code=exc.code,
            message=exc.message,
            task_id=str(exc.task_id) if exc.task_id is not None else None,
            retryable=exc.retryable,
            details=dict(exc.details),
            trace_id=request.state.trace_id,
        )
        request.app.state.logger.warning(
            exc.message,
            extra={
                "service": "core_service",
                "phase": "http_error",
                "event": "app_error",
                "code": exc.code,
                "task_id": exc.task_id,
                "trace_id": request.state.trace_id,
                "status_code": exc.status_code,
            },
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        payload = ErrorResponse(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            retryable=False,
            details={"errors": exc.errors()},
            trace_id=request.state.trace_id,
        )
        request.app.state.logger.warning(
            "Request validation failed.",
            extra={
                "service": "core_service",
                "phase": "http_validation",
                "event": "validation_error",
                "trace_id": request.state.trace_id,
                "status_code": 422,
            },
        )
        return JSONResponse(status_code=422, content=payload.model_dump())

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok"}

    return app


def main() -> None:
    uvicorn.run(
        "apps.core_service.app.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )


if __name__ == "__main__":
    main()
