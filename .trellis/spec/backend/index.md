# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This repository is still in a design-first stage. There is no committed backend
service implementation yet, so the backend guidelines in this directory are
bootstrapped from the agreed project artifacts:

- `requirement.md`
- `design.md`
- `table-schema.md`

Treat these files as the current source of truth for backend conventions until
real code exists. When implementation lands, replace design-only references with
real code references as soon as possible.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Service boundaries, module layout, file naming | Bootstrapped from design |
| [Database Guidelines](./database-guidelines.md) | PostgreSQL, pgvector, JSONB, MinIO boundaries | Bootstrapped from schema and design |
| [Task Pipeline Contracts](./task-pipeline-contracts.md) | HTTP, queue, MinIO, and task-status contracts for async parser flow | Executable contract |
| [Error Handling](./error-handling.md) | Task lifecycle failures vs business no-data states | Bootstrapped from workflow design |
| [Quality Guidelines](./quality-guidelines.md) | Required patterns, forbidden patterns, review gates | Bootstrapped from architecture docs |
| [Logging Guidelines](./logging-guidelines.md) | Structured logs for async pipeline tracing | Bootstrapped from workflow design |

---

## Pre-Development Checklist

Read this index first, then read the detailed guides that match the task:

1. `directory-structure.md` for package/service placement.
2. `database-guidelines.md` for schema, storage, and migration work.
3. `error-handling.md` and `logging-guidelines.md` for API, queue, and worker flows.
4. `quality-guidelines.md` before opening a PR or reviewing backend changes.
5. `../guides/cross-layer-thinking-guide.md` when the change affects API payloads,
   queue contracts, storage contracts, or the PDF/BBox flow into the frontend.

---

## Scope Reminder

The design establishes a strict split between:

- CPU business services: API gateway, orchestration, routing, normalization,
  persistence, traceability APIs.
- GPU parser service: MinerU execution and parse artifact generation only.

Do not collapse those concerns into a single service unless the architecture
decision is intentionally changed and the design docs are updated together.
