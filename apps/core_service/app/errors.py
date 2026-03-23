from collections.abc import Mapping
from typing import Any


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
        task_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = dict(details or {})
        self.task_id = task_id


class DependencyBoundaryError(Exception):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason or self.__class__.__name__


class StorageClientError(DependencyBoundaryError):
    pass


class QueueClientError(DependencyBoundaryError):
    pass


class QueuePayloadError(Exception):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason or self.__class__.__name__
