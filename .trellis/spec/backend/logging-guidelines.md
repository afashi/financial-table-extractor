# Logging Guidelines

> How logging is done in this project.

---

## Overview

The project uses the standard `logging` module with a custom JSON formatter in
`apps/core_service/app/logging_config.py`.

- Logs are emitted as JSON strings.
- `configure_logging(level_name)` is shared by both services.
- Operational context is passed through `extra={...}` fields instead of being
  embedded into the message string.

This is required because the system crosses HTTP, database, Redis, MinIO, and
worker boundaries.

---

## Log Levels

- `INFO`
  - normal lifecycle events such as task creation, dedup hits, task dispatch,
    parser start, parser completion, and parser-service startup
- `WARNING`
  - client or boundary issues that are expected and recoverable in-process, such
    as `AppError`, request validation failures, or queue messages referencing a
    missing task
- `ERROR`
  - unrecoverable dependency failures or task lifecycle failures, such as queue
    publish failures, parser download failures, parse failures, or database
    writeback failures
- `DEBUG`
  - not used heavily yet, but reserved for temporary low-level diagnostics

---

## Structured Logging

Every log line starts with the formatter-provided fields:

- `timestamp`
- `level`
- `logger`
- `message`

When adding backend logs, keep these extra fields stable whenever they apply:

- `service`
- `phase`
- `event`
- `task_id`
- `trace_id`
- `doc_type`
- `queue_name`
- `object_key`
- `code`
- `reason`

Do not build ad hoc keys for the same concept in different files. For example,
use `task_id`, not `taskId` in one place and `job_id` in another.

---

## What to Log

- Service startup and health-related milestones.
- Task lifecycle transitions such as `task_created`, `task_deduplicated`,
  `task_dispatched`, `parse_started`, `parse_completed`, and `parse_failed`.
- External-boundary failures with enough detail to reproduce the failing call:
  queue name, object key, failure code, and exception class name.
- Request and worker correlation data. HTTP flows use the middleware-generated
  `trace_id`; parser worker flows generate a per-message trace id.

---

## What NOT to Log

- Raw PDF bytes or full parser artifact payloads.
- Secrets from settings such as MinIO credentials or database URLs.
- Entire unredacted validation-error payloads when a summary and structured
  error list are enough.
- Duplicate hand-written context in the message string when it already exists in
  structured fields.

---

## Examples

- `apps/core_service/app/logging_config.py`: JSON formatter and idempotent root
  logger setup.
- `apps/core_service/app/services/task_service.py`: `task_created`,
  `task_deduplicated`, `task_dispatched`, and `task_dispatch_failed` log events.
- `apps/core_service/app/main.py`: HTTP-side warning logs for `AppError` and
  validation errors.
- `apps/parser_service/app/services/parser_worker.py`: worker logs for queue
  payload failures, parser start, parser completion, and parser failure.

---

## Common Mistakes

- Logging only a free-form sentence without `service`, `phase`, `event`, or
  `trace_id`.
- Logging secret-bearing configuration values.
- Using inconsistent event names for the same lifecycle step across services.
- Emitting large payload dumps instead of stable identifiers such as `task_id`
  and `object_key`.
