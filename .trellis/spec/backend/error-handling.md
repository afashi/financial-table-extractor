# Error Handling

> How errors are handled in this project.

---

## Overview

This system is asynchronous and phase-based, so error handling must preserve
both transport semantics and business semantics:

- Infrastructure or contract failures are real errors and should drive retries,
  task failure states, or operator attention.
- Business outcomes such as `NOT_DISCLOSED` and `NOT_FIND` are valid extraction
  results, not exceptions.
- Every failure path must preserve task context, current phase, and enough data
  to diagnose which external boundary failed.

---

## Error Types

Use error categories that map cleanly to pipeline boundaries:

- Validation errors: malformed API input, unsupported `doc_type`, invalid queue
  payloads, invalid parser artifacts, invalid LLM responses.
- Dependency errors: PostgreSQL, Redis, MinIO, MinerU, or external LLM gateway
  failures.
- Workflow errors: illegal state transitions, missing task records, corrupted or
  missing object storage references.
- Business result states: `SUCCESS`, `NOT_DISCLOSED`, `NOT_FIND`. These must not
  be thrown as transport errors.

If custom exception classes are introduced, name them after those boundaries,
for example `ArtifactValidationError`, `StorageClientError`, or
`TaskStateConflictError`.

---

## Error Handling Patterns

- Validate at every external boundary with explicit schemas. API payloads,
  queue messages, parser artifacts, and LLM output must be treated as untrusted
  input.
- Update task status explicitly on parser lifecycle boundaries:
  - `QUEUED -> PARSING -> PARSED`
  - `PARSING -> FAILED` on parse failure
  - `PARSED -> COMPLETED` or `PENDING_REVIEW` after extraction
- Surface duplicate-upload hits as normal business responses that return the
  existing task reference, not as hard failures.
- Treat missing target data carefully:
  - chapter found but target absent after fallback -> `NOT_DISCLOSED`
  - chapter not found at all -> `NOT_FIND`
- Keep retry decisions close to the failing boundary. Storage or queue outages
  are retryable; malformed artifacts and violated contracts are not.
- Never swallow errors after only logging them. Persist enough context for the
  task audit trail and return a stable error code upstream.

---

## API Error Responses

No final API contract file exists yet, so use a single response envelope when
the first HTTP endpoints are implemented:

```json
{
  "code": "OBJECT_NOT_FOUND",
  "message": "content_list.json is missing for task 102400001",
  "task_id": "102400001",
  "retryable": false,
  "details": {},
  "trace_id": "req-102400001"
}
```

Guidelines:

- Use `4xx` for caller mistakes or invalid inputs.
- Use `5xx` for dependency outages, internal contract violations, or worker
  failures.
- Do not encode long-running extraction status as HTTP exceptions when the task
  should instead be inspected via its persisted status record.

---

## Examples

- `design.md`: Phase 1 defines explicit parse success and parse failure events.
- `design.md`: Phase 3 defines when to return `NOT_DISCLOSED` vs `NOT_FIND`.
- `requirement.md`: section 3.4 defines the null and no-data semantics that must
  not be flattened into generic errors.

---

## Common Mistakes

- Returning HTTP 500 for `NOT_FIND` or `NOT_DISCLOSED`.
- Logging a dependency error without updating task state or storing failure
  context.
- Reusing the same catch-all exception for validation failures and retryable
  infrastructure failures.
- Losing `task_id`, phase, or target table context in the error path.
