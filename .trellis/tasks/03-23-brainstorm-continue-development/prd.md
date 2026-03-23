# brainstorm: continue development

## Goal

Decide the next concrete implementation task for the project and capture the
scope in a way that can flow directly into Trellis task execution. The project
already has architecture, schema, and guideline documents, but almost no real
application code yet.

## What I already know

* The previous bootstrap task is complete and archived.
* There is currently no active Trellis task.
* The repository is still at an early implementation stage.
* `main.py` is only a hello-world stub.
* `pyproject.toml` defines the package but currently has no dependencies.
* Project docs already define a target architecture:
  * CPU-side core service
  * GPU-side parser service
  * PostgreSQL, Redis, MinIO
  * Vue 3 frontend for traceability review
* The backend guidelines require:
  * route handlers to stay thin
  * persistence, business logic, and integrations to stay separate
  * task statuses and error payloads to remain explicit
  * cross-layer contracts to be defined at boundaries

## Assumptions (temporary)

* The next task should create real implementation scaffolding rather than more
  documentation.
* The safest first implementation step is backend-first, because API and task
  contracts will anchor both parser and frontend work.

## Open Questions

* None currently.

## Requirements (evolving)

* Build the first real implementation slice as backend skeleton plus task
  contract.
* Keep the first slice small enough to implement and verify incrementally.
* Align the slice with the documented architecture and project guidelines.
* Use this slice to establish the first stable API and task-state contract that
  later parser and frontend work can depend on.
* Use real PostgreSQL-backed persistence rather than only in-memory storage.
* Limit the first persisted backend slice to `t_task`.
* Accept a real uploaded file in `POST /api/v1/extract`, but stop after task
  creation, deduplication, and response.
* Use SQLAlchemy 2 + Alembic + async PostgreSQL access as the persistence stack.
* Generate `task_id` as a Snowflake-style `BIGINT`, matching the documented
  schema contract.
* Preserve the documented deduplication rule on
  `(file_hash, file_size, doc_type)`.
* Expose at least:
  * `POST /api/v1/extract`
  * `GET /tasks/{task_id}`

## Acceptance Criteria (evolving)

* [x] A first implementation slice is explicitly chosen.
* [x] The chosen slice has a clear MVP scope boundary.
* [x] The chosen slice can be turned into a Trellis implementation task without
      further repo discovery.
* [ ] The backend skeleton starts successfully with configured database access.
* [ ] `POST /api/v1/extract` accepts a real uploaded file and `doc_type`,
      computes `file_hash` and `file_size`, performs deduplication, and
      persists/returns a task record.
* [ ] `GET /tasks/{task_id}` returns the persisted task contract.
* [ ] `task_id` is returned as a Snowflake-style `BIGINT` contract value.

## Definition of Done (team quality bar)

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Docs/notes updated if behavior changes
* Rollout/rollback considered if risky

## Out of Scope (explicit)

* Building the entire end-to-end system in one task
* Final production deployment design
* Non-essential UI polish before core contracts exist

## Technical Notes

* Existing implementation baseline inspected:
  * `main.py`
  * `pyproject.toml`
* Existing architecture and behavior docs already available in repo:
  * `requirement.md`
  * `design.md`
  * `table-schema.md`
* Design and schema details confirmed during brainstorm:
  * `design.md` defines `POST /api/v1/extract`
  * `design.md` requires `doc_type` at intake
  * `table-schema.md` defines `t_task`
  * `table-schema.md` defines dedup uniqueness on
    `(file_hash, file_size, doc_type)`
* MVP boundary selected during brainstorm:
  * real file upload
  * real PostgreSQL persistence
  * only `t_task` in first schema slice
  * no MinIO, Redis, or parser execution yet
* Persistence stack selected during brainstorm:
  * FastAPI
  * SQLAlchemy 2
  * Alembic
  * async PostgreSQL driver
* ID contract selected during brainstorm:
  * Snowflake-style `BIGINT`
* Initial API surface selected during brainstorm:
  * `POST /api/v1/extract`
  * `GET /tasks/{task_id}`
* Existing Trellis guidelines were just bootstrapped and should guide the first
  real implementation task.
* Relevant specs re-read during brainstorm:
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/backend/database-guidelines.md`
  * `.trellis/spec/backend/error-handling.md`
  * `.trellis/spec/backend/logging-guidelines.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`

## Research Notes

### What similar FastAPI stacks commonly do

* Use FastAPI with SQLAlchemy 2 and Alembic for a mature migration and model
  workflow.
* Use async PostgreSQL drivers such as `asyncpg` with an async SQLAlchemy
  engine when the API is async-first.
* Keep database access behind repository functions or classes instead of in route
  handlers.

### Constraints from this repo/project

* The project already requires explicit contracts, task states, and thin route
  handlers.
* The first slice is intentionally narrow: `t_task` only.
* The system will later need richer PostgreSQL features such as JSONB and
  `pgvector`, so the DB layer should not paint the project into a corner.

### Feasible approaches here

**Approach A: SQLAlchemy 2 + Alembic + asyncpg** (Recommended)

* How it works:
  * SQLAlchemy 2 declarative model for `t_task`
  * Alembic manages schema revisions
  * FastAPI uses async sessions
  * repository layer handles persistence
* Pros:
  * mature ecosystem
  * strong migration story
  * easy to grow into future schema complexity
  * clean separation between API schemas and DB models
* Cons:
  * more boilerplate up front than lighter wrappers

**Approach B: SQLModel + Alembic**

* How it works:
  * SQLModel model doubles as typed ORM-ish model
  * Alembic still manages migrations
  * FastAPI integrates naturally with SQLModel-style typing
* Pros:
  * less boilerplate
  * friendly for small CRUD APIs
* Cons:
  * less explicit separation between transport and persistence
  * may become awkward as schema and boundary complexity grows

**Approach C: psycopg/asyncpg + handwritten SQL + migration tool**

* How it works:
  * direct SQL in repository layer
  * explicit SQL migrations
  * no ORM model layer
* Pros:
  * maximum SQL clarity and control
  * minimal ORM abstraction
* Cons:
  * more manual mapping work
  * higher upfront cost for routine CRUD and validation wiring
  * less ergonomic for a brand-new scaffold

### Chosen approach

* Selected: **Approach A**
* Reason:
  * best fit for async FastAPI
  * mature migration story
  * keeps API and DB boundaries explicit
  * scales better into the later JSONB/vector-heavy schema

## Decision (ADR-lite)

**Context**: The repository has architecture and schema documents, but almost no
real application code. The first implementation task needs to unlock future
parser and frontend work without trying to build the full system at once.

**Decision**: Start with backend skeleton plus task contract, using a real
PostgreSQL-backed persistence layer, limit the first persisted slice to
`t_task`, use SQLAlchemy 2 + Alembic + async PostgreSQL access, and keep the
public `task_id` contract as Snowflake-style `BIGINT`.

**Consequences**:

* Gives the project a real executable backend entry point.
* Establishes stable task lifecycle and API payload shapes early.
* Delays full parser integration and frontend work until contracts exist.
* Keeps the first public API aligned with the documented schema.
* Forces the first implementation to include a stable ID generator and explicit
  dedup behavior.
