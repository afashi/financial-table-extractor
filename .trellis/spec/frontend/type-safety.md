# Type Safety

> Type safety patterns in this project.

---

## Overview

The frontend type system should mirror backend contracts closely enough that
financial semantics are not accidentally erased in the UI layer. The main risks
in this project are:

- bigint identifiers crossing into JavaScript
- status unions being flattened into generic strings
- `null` cell values being confused with `"NOT_DISCLOSED"` or `"NOT_FIND"`
- free-form BBox objects drifting away from backend shape

---

## Type Organization

- Keep transport contracts in a dedicated `types/` area.
- Keep feature-specific view models near the feature that owns them.
- Use explicit mapper functions when converting backend payloads into display
  models. Do not let templates perform contract-to-view transformations inline.
- When shared contracts eventually exist across frontend and backend, prefer one
  source of truth over hand-maintained duplicate enums.

---

## Validation

- No runtime validation library has been selected yet. Until one is adopted,
  validate API payloads at the `services/api/` boundary with explicit parser
  functions or type guards.
- Validate the fields that carry business meaning:
  - `task_id`
  - `status`
  - `data_status`
  - `extraction_route`
  - `confidence_score`
  - `bbox`
- If the project later adopts a schema library, keep schemas close to transport
  contracts and make frontend mappers consume validated data only.

---

## Common Patterns

- Treat Snowflake-style backend IDs as strings in the browser, even if the
  backend stores them as `BIGINT`.
- Model task status and data status as literal unions, not loose strings.
- Model `SUCCESS`, `NOT_DISCLOSED`, and `NOT_FIND` as discriminated states so
  the UI can render each path explicitly.
- Type BBox as a structured array of page-bound rectangles instead of
  `Record<string, unknown>`.
- Keep unit and currency as explicit enums or literal unions because they affect
  user trust and downstream interpretation.

---

## Forbidden Patterns

- Using `any` for backend responses.
- Blanket `as` casts over unvalidated API payloads.
- Treating `task_id` or other `BIGINT` fields as JavaScript numbers.
- Collapsing `null`, `NOT_DISCLOSED`, and `NOT_FIND` into one "empty" branch.
- Defaulting missing `bbox`, `confidence_score`, or status fields silently.

---

## Examples

- `table-schema.md`: documents `BIGINT` task IDs and the persisted result shape.
- `design.md`: `rule.json` and `extracted_result.json` examples define stable
  transport contracts.
- `requirement.md`: section 3.4 defines the null and no-data semantics the UI
  must preserve.
