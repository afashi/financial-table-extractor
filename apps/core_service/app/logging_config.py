import json
import logging
from datetime import UTC, datetime
from typing import Any

_STANDARD_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    """Simple JSON formatter that preserves extra fields for task tracing."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value if self._is_json_safe(value) else repr(value)

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)

    @staticmethod
    def _is_json_safe(value: Any) -> bool:
        return isinstance(value, str | int | float | bool) or value is None


def configure_logging(level_name: str) -> None:
    root_logger = logging.getLogger()

    if root_logger.handlers:
        root_logger.setLevel(level_name.upper())
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger.setLevel(level_name.upper())
    root_logger.addHandler(handler)
