# Directory Structure

> How backend code is organized in this project.

---

## Overview

The backend has not been implemented yet, but the project design already fixes
the main service boundaries:

- A CPU-side core service owns API handling, task orchestration, routing,
  normalization, confidence scoring, persistence, and traceability APIs.
- A GPU-side parser service owns MinerU execution and parse artifact creation.
- Shared code should be limited to stable contracts, enums, and utilities.

The layout below is the target structure future backend code should follow.

---

## Directory Layout

```text
apps/
├── core-service/
│   ├── app/
│   │   ├── api/
│   │   ├── workers/
│   │   ├── pipelines/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── strategies/
│   │   ├── clients/
│   │   └── settings.py
│   └── tests/
├── parser-service/
│   ├── app/
│   │   ├── consumers/
│   │   ├── services/
│   │   ├── schemas/
│   │   ├── clients/
│   │   └── settings.py
│   └── tests/
└── shared/
    ├── contracts/
    ├── enums/
    └── utils/
```

---

## Module Organization

- Put HTTP endpoints only in `api/`. They validate input, invoke application
  services, and return task-oriented responses. They should not run parsing or
  table extraction logic inline.
- Put queue consumers and asynchronous job entry points in `workers/` or
  `consumers/`. They map external events to pipeline calls and status updates.
- Put extraction, routing, normalization, and confidence logic in `pipelines/`
  and `services/`, not inside route handlers or repositories.
- Put persistence code in `repositories/`. Repository code should know SQL and
  table layout, but not extraction business rules.
- Put Pydantic request, response, event, and artifact models in `schemas/`.
- Put table-specific cleanup or reshaping code in `strategies/`. This matches
  the pluggable transformation engine described in the design.
- Keep third-party integration wrappers in `clients/` for PostgreSQL, Redis,
  MinIO, MinerU, and the LLM gateway.
- Keep `shared/` intentionally small. If a module is only used by one service,
  keep it local to that service.

---

## Naming Conventions

- Use `snake_case` for Python modules, packages, and functions.
- Use explicit entrypoint names such as `main.py`, `worker.py`, and
  `settings.py`.
- Use suffixes that reveal boundary intent:
  - `*Request`, `*Response`, `*Event`, `*Artifact` for schemas
  - `*_repository.py` for database access
  - `*_client.py` for third-party integrations
  - `*_strategy.py` for post-processing plugins
- Name pipeline modules after a phase or capability, for example
  `semantic_routing.py`, `normalization.py`, or `confidence_scoring.py`.
- Keep service names aligned with the architecture terms already used in the
  project documents: `core-service`, `parser-service`, `traceability`, and
  `transformation`.

---

## Examples

Use these project artifacts as the current structural references until real code
exists:

- `design.md`: sections "3.1" and "3.2" define the CPU/GPU service split.
- `design.md`: section "4.1" defines the phase-based backend workflow.
- `table-schema.md`: defines which concerns belong in the relational model
  rather than object storage.
