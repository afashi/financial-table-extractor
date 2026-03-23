# Logging Guidelines

> How logging is done in this project.

---

## Overview

The backend is an asynchronous multi-service pipeline. Logs must therefore be
structured enough to answer these questions quickly:

- Which task is this log line about?
- Which service and phase produced it?
- Was the issue caused by storage, parsing, routing, fallback, normalization, or
  persistence?
- Can the operator safely retry?

The logging library has not been selected yet, but the output format must be
structured JSON or equivalent key-value logs.

---

## Log Levels

- `DEBUG`: detailed scoring inputs, rule matching traces, and other diagnostic
  data used during development or controlled incident debugging.
- `INFO`: task accepted, dedup hit, queue publish, parser started/completed,
  extraction completed, result persisted, review queue transition.
- `WARN`: fallback path triggered, missing unit metadata, degraded confidence,
  partial retrigger, unexpected but recoverable data shape.
- `ERROR`: unrecoverable dependency failure, contract violation, parser failure,
  or status transition that leaves the task unusable.

---

## Structured Logging

Every production log should include the fields that make async tracing possible:

- `service`
- `phase`
- `event`
- `task_id`
- `doc_type`
- `trace_id`
- `duration_ms` when relevant

Add boundary-specific fields when useful:

- `queue_name`
- `object_key`
- `rule_id`
- `target_table_code`
- `confidence_score`
- `retry_count`

Keep log field names stable across services so task traces can be correlated
without custom parsing for each subsystem.

---

## What to Log

- API intake: file hash, file size, doc type, dedup hit or miss, created task ID.
- Queue activity: publish and consume events for parser and extractor workers.
- Parser lifecycle: source object key, parse started/completed/failed, artifact
  validation outcome.
- Routing and extraction: chapter match results, anchor rule match outcome,
  fallback trigger reason, extracted target table code.
- Normalization and scoring: detected unit/currency, confidence penalties, and
  whether the result entered review.
- Manual retrigger flows: which target tables were rerun and which records were
  replaced.

---

## What NOT to Log

- Raw PDF bytes or entire PDF text dumps.
- Full `content_list.json` payloads.
- Secrets, credentials, tokens, or signed URLs.
- Full LLM prompts or responses unless they are explicitly redacted and the
  logging path is temporary and approved.
- Large extracted financial payloads when a task ID and target table code are
  enough to locate the data.

---

## Examples

- `design.md`: Phases 0 through 6 define the events that need traceable logs.
- `requirement.md`: sections 3.6 and 3.7 explain why confidence and BBox data
  need operator-visible traceability.
- `table-schema.md`: shows the persistence keys logs should correlate with,
  especially `task_id`, `target_table_code`, and review state.
