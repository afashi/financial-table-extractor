# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

Backend quality in this project is mostly about preserving architectural
boundaries and business correctness. Financial extraction is a low-tolerance
domain; a small semantic shortcut can be more dangerous than a crash.

Because the repository is still at the bootstrap stage, treat these guidelines
as the minimum bar for the first implementation.

---

## Forbidden Patterns

- Running MinerU parsing work inside the HTTP request/response thread.
- Mixing parser-service responsibilities with core-service business logic.
- Treating `NOT_DISCLOSED`, `NOT_FIND`, and `null` as interchangeable.
- Hard-coding confidence thresholds or unit defaults in multiple places.
- Writing one monolithic extraction function that mixes routing, extraction,
  normalization, persistence, and traceability.
- Mutating the canonical parser artifact after it is written to object storage.
- Returning ad hoc status strings that do not match the documented task or data
  status values.

---

## Required Patterns

- Preserve the documented phase boundaries from `design.md`.
- Validate every boundary payload with explicit schemas.
- Keep persistence, business logic, and third-party integration concerns in
  separate modules.
- Make confidence penalties explicit and reviewable.
- Keep the rule-first, model-fallback behavior deterministic and auditable.
- Register special-case post-processing through a strategy mechanism instead of
  sprinkling table-specific exceptions across the pipeline.
- Keep deduplication and partial re-trigger flows idempotent.

---

## Testing Requirements

- No runnable project stack is committed yet, so bootstrap changes should at
  least pass syntax review, import review, type review, and contract review.
- The first backend implementation should add unit tests for:
  - routing rule evaluation
  - null and no-data normalization
  - confidence score calculation
  - transformation strategy selection
- Add integration tests for task lifecycle transitions and partial retrigger
  flows.
- Add contract tests against the documented `rule.json` and
  `extracted_result.json` formats.

---

## Code Review Checklist

- Does the change preserve the CPU/GPU service split?
- Are schema, API, and storage contracts updated together?
- Are task statuses and data statuses still unambiguous?
- Is low-confidence handling still visible and deterministic?
- Are logs structured enough to debug a task end to end?
- Does the code avoid mutating canonical parser artifacts?
- Can the flow be retried without corrupting task state or duplicating results?

---

## Examples

- `requirement.md`: sections 3.3 through 3.7 define the user-visible accuracy
  and traceability bar.
- `design.md`: section 4.2.1 defines the partial re-trigger workflow that review
  logic must preserve.
- `table-schema.md`: exposes which fields are critical enough to deserve tests
  and review focus.
