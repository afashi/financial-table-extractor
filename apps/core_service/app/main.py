import logging
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apps.core_service.app.api.router import api_router
from apps.core_service.app.clients.database import DatabaseClient
from apps.core_service.app.errors import AppError
from apps.core_service.app.logging_config import configure_logging
from apps.core_service.app.schemas.errors import ErrorResponse
from apps.core_service.app.settings import Settings, get_settings
from apps.shared.utils.snowflake import SnowflakeIdGenerator


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    logger = logging.getLogger(app_settings.app_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database_client = DatabaseClient(app_settings.database_url)
        await database_client.healthcheck()
        app.state.settings = app_settings
        app.state.logger = logger
        app.state.database_client = database_client
        app.state.task_id_generator = SnowflakeIdGenerator(
            worker_id=app_settings.task_id_node_id,
            epoch_ms=app_settings.task_id_epoch_ms,
        )
        yield
        await database_client.dispose()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.include_router(api_router)

    @app.middleware("http")
    async def attach_trace_id(request: Request, call_next):
        trace_id = uuid4().hex
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

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
