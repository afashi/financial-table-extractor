# Error Handling

> How errors are handled in this project.

---

## Overview

The current backend separates errors by boundary:

- `AppError` is the HTTP-facing error type returned by the FastAPI app.
- `StorageClientError` and `QueueClientError` wrap dependency failures close to
  the adapter boundary.
- `QueuePayloadError` marks malformed queue data and is handled inside the
  worker loop.
- Parser-engine failures use `ParserEngineError`.

The design goal is explicit failure, not silent fallback. When a boundary fails,
the code either returns a stable error envelope to the caller or persists task
state to `FAILED` and logs the reason.

---

## Error Types

- `AppError` in `apps/core_service/app/errors.py`
  - carries `code`, `message`, `status_code`, `retryable`, `details`, and
    optional `task_id`
  - is turned into `ErrorResponse` by the global exception handler in
    `apps/core_service/app/main.py`
- `DependencyBoundaryError`
  - base type for adapter-level failures that should not leak raw vendor
    exceptions
- `StorageClientError` and `QueueClientError`
  - wrap MinIO and Redis failures with a stable `reason`
- `QueuePayloadError`
  - separates invalid queue data from infrastructure outages
- `ParserEngineError`
  - marks parser-specific failures that should transition a task to `FAILED`

---

## Error Handling Patterns

- Validate external input early and raise `AppError` for request-level failures.
  File upload validation currently happens in both `build_file_fingerprint(...)`
  and the start of `TaskService.create_extract_task(...)`.
- Catch library-specific exceptions near the boundary and wrap them in project
  exceptions with a stable `reason`, as shown in `queue.py` and
  `object_storage.py`.
- Roll back the current transaction before translating SQLAlchemy failures into
  `AppError`. `TaskService` does this for create, fetch, and re-queue flows.
- When dispatch fails after a task row already exists, persist `TaskStatus.FAILED`
  and a stable `remark` before re-raising the API error.
- In worker code, prefer logging plus status writeback over bubbling exceptions
  into the infinite loop. `ParserWorker` updates task state to `FAILED` and
  returns control to the caller.
- Treat invalid queue payloads as explicit errors, but do not crash the worker
  loop. Log them and discard the bad message.

---

## API Error Responses

All HTTP-side failures use `ErrorResponse` from
`apps/core_service/app/schemas/errors.py`:

```json
{
  "code": "QUEUE_UNAVAILABLE",
  "message": "Failed to publish the parser task message.",
  "task_id": "1234567890",
  "retryable": true,
  "details": {
    "reason": "ConnectionError"
  },
  "trace_id": "3d6aa4e3a9f346e2a6b6b7f1c7fd2c50"
}
```

Rules:

- Use `4xx` for caller or validation mistakes, for example
  `INVALID_FILE_UPLOAD` and `TASK_NOT_FOUND`.
- Use `503` for dependency outages or database unavailability.
- Always include `trace_id` in HTTP error responses.
- Include `task_id` whenever a failure happened after a task was created.

---

## Examples

- `apps/core_service/app/main.py`: global handlers for `AppError` and
  `RequestValidationError`.
- `apps/core_service/app/services/task_service.py`: rollback + translate
  SQLAlchemy failures, plus persisted failure state for queue and object-storage
  dispatch errors.
- `apps/parser_service/app/services/parser_worker.py`: queue payload discard,
  parser failure handling, and `FAILED` state persistence.
- `apps/core_service/app/clients/object_storage.py`: vendor-exception wrapping
  into `StorageClientError`.

---

## Common Mistakes

- Raising raw `RedisError`, `SQLAlchemyError`, or MinIO exceptions past the
  project boundary.
- Logging a failure without updating task state when the task has already moved
  into an owned lifecycle.
- Returning inconsistent `remark` strings for worker failures. The project uses
  stable remarks that tests assert against.
- Swallowing queue payload validation problems instead of logging them with a
  clear code and reason.
