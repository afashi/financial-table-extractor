# Directory Structure

> How backend code is organized in this project.

---

## Overview

The backend is organized by service boundary first, then by responsibility
inside each service. The current repository structure is already the baseline
to follow:

- `apps/core_service/app/` owns FastAPI setup, request-scoped dependencies, task
  APIs, infrastructure clients, repositories, and task orchestration.
- `apps/parser_service/app/` owns the parser worker loop and parser-engine
  implementation.
- `apps/shared/` holds stable enums and low-level utilities that are safe to
  reuse across both services.
- `tests/` mirrors service boundaries and relies on fake adapters instead of
  real infrastructure.

---

## Directory Layout

```text
apps/
├── core_service/
│   └── app/
│       ├── api/
│       │   ├── dependencies.py
│       │   ├── router.py
│       │   └── routes/
│       ├── clients/
│       ├── db/
│       │   ├── base.py
│       │   └── models/
│       ├── repositories/
│       ├── schemas/
│       ├── services/
│       ├── utils/
│       ├── errors.py
│       ├── logging_config.py
│       ├── main.py
│       └── settings.py
├── parser_service/
│   └── app/
│       ├── schemas/
│       ├── services/
│       ├── main.py
│       └── settings.py
└── shared/
    ├── enums/
    └── utils/

alembic/
└── versions/

tests/
├── conftest.py
├── core_service/
└── parser_service/
```

---

## Module Organization

- Put HTTP routing and dependency wiring under `apps/core_service/app/api/`.
  Route functions should stay thin and delegate to services.
- Put business workflow orchestration under `apps/core_service/app/services/`.
  `TaskService` is the current reference for "service owns flow + transaction
  boundary + logging".
- Put direct persistence logic under `apps/core_service/app/repositories/`.
  Repository methods accept an `AsyncSession` and do not own commits.
- Put infrastructure adapters under `apps/core_service/app/clients/`.
  The base class and the concrete implementation live together in the same
  module today, for example `queue.py` and `object_storage.py`.
- Put SQLAlchemy metadata and models under `apps/core_service/app/db/`.
  Keep `base.py` small and import concrete models through
  `apps/core_service/app/db/models/__init__.py`.
- Put Pydantic request, response, and queue contracts under
  `apps/core_service/app/schemas/`.
- Put parser-specific runtime logic under `apps/parser_service/app/services/`.
  The parser service currently reuses shared task contracts and infrastructure
  adapters from `core_service` instead of duplicating them.
- Keep only truly shared pieces in `apps/shared/`, such as `DocumentType`,
  `TaskStatus`, and `SnowflakeIdGenerator`.

---

## Naming Conventions

- Use `snake_case` for packages, modules, functions, and helper names.
- Use explicit file names that reveal responsibility:
  - `task_service.py` for orchestration logic
  - `task_repository.py` for database access
  - `queue.py` and `object_storage.py` for integration adapters
  - `settings.py` for environment-backed configuration
  - `logging_config.py` for logger setup
- Keep route modules grouped by resource, for example
  `apps/core_service/app/api/routes/tasks.py`.
- Name Pydantic schemas by boundary intent, for example
  `TaskSubmissionResponse`, `TaskReadResponse`, `ParserTaskMessage`, and
  `ErrorResponse`.
- Keep object-key builders and hashing helpers in `utils/` only when they are
  pure, boundary-agnostic helpers.

---

## Examples

- `apps/core_service/app/main.py`: application assembly, middleware, lifespan,
  and global exception handlers.
- `apps/core_service/app/services/task_service.py`: service-layer reference for
  dependency injection, transaction ownership, and structured logging.
- `apps/parser_service/app/services/parser_worker.py`: worker-side reference for
  queue consumption, task-state transitions, and infrastructure failure
  handling.
- `tests/conftest.py`: canonical testing layout with fake object storage, queue,
  database client, and repository implementations.
