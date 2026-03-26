# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

Backend quality in this project is defined by a few concrete rules:

- keep service boundaries explicit
- expose failures instead of hiding them behind fallbacks
- separate orchestration, persistence, and infrastructure adapters
- keep contracts stable across HTTP, queue, database, and object storage
- prove behavior with automated tests

Project-wide guardrails in `AGENTS.md` also apply here, including limits on
function size, nesting, cyclomatic complexity, magic numbers, and the
debug-first "no silent fallbacks" policy.

---

## Forbidden Patterns

- Putting orchestration logic directly in FastAPI route handlers.
- Committing database transactions inside repositories instead of the owning
  service or worker flow.
- Constructing queue payloads or object-storage keys inline in multiple places
  when shared helpers or schemas already exist.
- Returning numeric task IDs in public JSON responses. The API contract uses
  decimal strings to avoid precision issues in other runtimes.
- Catching broad exceptions only to return fake success or swallow the failure.
- Duplicating stable shared contracts across `core_service`, `parser_service`,
  and `shared`.

---

## Required Patterns

- Use dependency injection through `create_app(...)`, request dependencies, or
  constructor parameters. `TaskService` and `ParserWorker` are the reference
  implementations.
- Use explicit Pydantic models for boundary payloads such as
  `ParserTaskMessage`, `TaskSubmissionResponse`, and `ErrorResponse`.
- Keep pure helpers in `utils/` and keep them side-effect free.
- Convert third-party exceptions into project-specific boundary errors close to
  the integration point.
- Use shared enums (`DocumentType`, `TaskStatus`) instead of ad hoc strings in
  business logic.
- Keep fake adapters in tests instead of relying on live PostgreSQL, Redis, or
  MinIO for normal unit/integration coverage.

---

## Testing Requirements

- Run Ruff before finishing backend work. Current project command:
  `python3 -m ruff check apps alembic tests`
- Run pytest for backend verification. Current project command:
  `python3 -m pytest -q`
- Keep task lifecycle behavior covered with tests. The current baseline includes:
  - fresh upload and fetch flow
  - duplicate dedup flow
  - failed dispatch persistence
  - parser worker `QUEUED -> PARSING -> PARSED`
  - parser worker failure paths for parse and storage errors
- When changing a contract, update the executable contract doc and the
  corresponding tests in the same change.

---

## Code Review Checklist

- Does the change preserve the current service split between `core_service` and
  `parser_service`?
- Are route handlers still thin and delegating to services?
- Are transaction boundaries explicit and still owned by the orchestration
  layer?
- Are task status transitions, error codes, and failure remarks still stable?
- Do logs still include enough structured fields to trace a task end to end?
- Are shared helpers and schemas reused instead of reimplemented?
- Are Ruff and pytest still green?

---

## Examples

- `apps/core_service/app/api/routes/tasks.py`: thin routing layer that delegates
  to `TaskService`.
- `apps/core_service/app/services/task_service.py`: service-layer ownership of
  orchestration, commits, rollbacks, and structured logging.
- `tests/conftest.py`: fake adapters used for repeatable tests without external
  infrastructure.
- `pyproject.toml`: authoritative Ruff and pytest configuration.
