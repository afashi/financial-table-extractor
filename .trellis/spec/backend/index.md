# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

The repository already has a working backend skeleton. The current shape is:

- `apps/core_service/app/`: FastAPI HTTP entrypoint, dependency wiring, task
  submission flow, infrastructure clients, repositories, and API schemas.
- `apps/parser_service/app/`: long-running parser worker, parser engine, and
  parser artifact handling.
- `apps/shared/`: enums and utilities shared across both services.
- `alembic/`: SQLAlchemy/Alembic migration history for relational schema
  changes.

These guidelines should describe the current implementation style, not a future
target architecture.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Service boundaries, module layout, file naming | Project-specific |
| [Database Guidelines](./database-guidelines.md) | SQLAlchemy async usage, migrations, table naming | Project-specific |
| [Task Pipeline Contracts](./task-pipeline-contracts.md) | HTTP, queue, MinIO, and task-status contracts for async parser flow | Executable contract |
| [Error Handling](./error-handling.md) | API errors, dependency boundary errors, worker failure handling | Project-specific |
| [Quality Guidelines](./quality-guidelines.md) | Required patterns, forbidden patterns, review gates | Project-specific |
| [Logging Guidelines](./logging-guidelines.md) | JSON logging, required extra fields, log-level usage | Project-specific |

---

## Pre-Development Checklist

Read this index first, then read the detailed guides that match the change:

1. `directory-structure.md` before adding or moving backend modules.
2. `database-guidelines.md` before changing SQLAlchemy models, repositories, or
   Alembic revisions.
3. `task-pipeline-contracts.md` before changing task submission endpoints, queue
   payloads, object-key conventions, or task lifecycle transitions.
4. `error-handling.md` and `logging-guidelines.md` before changing any external
   boundary, retry path, or worker loop.
5. `quality-guidelines.md` before review or merge.
6. `../guides/cross-layer-thinking-guide.md` when a change affects HTTP
   payloads, queue contracts, object storage paths, or task status values seen
   by other layers.

---

## Scope Reminder

The backend currently enforces a clear split:

- `core_service` accepts uploads, persists and fetches task state, stores the
  source PDF, and publishes parser work.
- `parser_service` consumes queue messages, runs the parser engine, writes the
  parser artifact, and updates task status.
- `shared` stays small and only holds stable enums and utilities that both
  services genuinely need.

Do not collapse those concerns into route handlers or a catch-all utility
module.
