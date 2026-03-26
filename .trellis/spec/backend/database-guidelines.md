# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

The current backend uses SQLAlchemy 2.x async APIs for runtime access and
Alembic for schema changes.

- Runtime engine and session factory live in
  `apps/core_service/app/clients/database.py`.
- Declarative metadata lives in `apps/core_service/app/db/base.py`.
- Concrete models live in `apps/core_service/app/db/models/`.
- Migrations live in `alembic/versions/`.

The current relational schema is intentionally small: `t_task` stores task
identity and lifecycle state, while large binary artifacts remain in object
storage.

---

## Query Patterns

- Keep `AsyncSession` ownership in the service or worker layer. Repository
  methods accept a session object; they do not create sessions internally.
- Use `session.get(Model, primary_key)` for direct primary-key lookups, as shown
  in `apps/core_service/app/repositories/task_repository.py`.
- Use explicit `select(...)` queries for non-primary-key reads. The task
  deduplication lookup uses `select(Task).where(...)` on the fingerprint tuple.
- Use `session.add(...)`, then `flush()` and `refresh()` inside repository
  methods to materialize generated state before returning.
- Keep `commit()` and `rollback()` in the caller that owns the business flow.
  `TaskService` and `ParserWorker` both follow this rule.
- Persist enum values as stable strings. `Task.status` and `Task.doc_type` are
  stored as `String(...)` columns and mapped back to `StrEnum` values in schema
  or service code.
- Keep timestamps timezone-aware and UTC-based. The `Task` model uses
  `DateTime(timezone=True)` and `utc_now()`.

---

## Migrations

- Create schema changes with Alembic under `alembic/versions/`.
- Keep `alembic/env.py` aligned with the current model package imports. New
  models must be imported into `apps/core_service/app/db/models/__init__.py`
  and reachable from `Base.metadata`.
- Prefer explicit migration operations such as `op.create_table(...)`,
  `op.create_index(...)`, and `sa.text(...)` defaults over opaque raw SQL.
- Keep upgrade and downgrade paths in the same revision file. The current
  `20260323_0001_create_t_task.py` migration is the reference.
- Run Alembic through the project virtual environment so it uses the same
  settings module and dependency set as the app.

---

## Naming Conventions

- Use `snake_case` for tables, columns, indexes, and revision files.
- Use the `t_` prefix for business tables. The current task table is `t_task`.
- Use `idx_<table>_<fields>` for indexes. The deduplication index is
  `idx_t_task_hash_size_doc_type`.
- Use `_time` suffixes for persisted timestamps, for example `create_time` and
  `update_time`.
- Keep externally visible lifecycle values uppercase and stable. Current task
  states come from `apps/shared/enums/task_status.py`.

---

## Examples

- `apps/core_service/app/clients/database.py`: async engine construction with
  `pool_pre_ping=True` and an `async_sessionmaker`.
- `apps/core_service/app/db/models/task.py`: canonical model layout, naming, and
  UTC timestamp defaults.
- `apps/core_service/app/repositories/task_repository.py`: repository methods
  with `session.get`, `select`, `flush`, and `refresh`.
- `alembic/versions/20260323_0001_create_t_task.py`: reference migration
  structure and index naming.

---

## Common Mistakes

- Committing or rolling back inside repository methods. That hides transaction
  boundaries from the business flow.
- Storing parser artifacts in PostgreSQL instead of object storage. The current
  design keeps PDFs and `content_list.json` outside the relational database.
- Adding a new model without importing it into `apps/core_service/app/db/models`
  and `alembic/env.py`, which makes Alembic autogeneration incomplete.
- Bypassing the shared enums and writing ad hoc status strings into the database.
