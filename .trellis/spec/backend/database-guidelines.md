# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

PostgreSQL is the system of record for business data, task state, routing rules,
and extracted results. `pgvector` is part of the relational data model for
semantic matching. MinIO stores large binary or semi-structured artifacts such
as source PDFs, `content_list.json`, and optional slice images.

Current schema contracts are documented in `table-schema.md`. Until migrations
and implementation code exist, that file is the authoritative database contract.

---

## Query Patterns

- Always deduplicate uploads by the full `(file_hash, file_size, doc_type)`
  tuple before a new task is queued. This is part of the business contract, not
  an optimization.
- Store large parse artifacts in MinIO and keep only stable references and
  extracted business data in PostgreSQL.
- Use scalar columns for high-value query predicates such as `task_id`,
  `target_table_code`, `status`, `needs_review`, and page ranges. Use `JSONB`
  for semi-structured payloads such as `path_fingerprints`, `anchor_rule`,
  `table_data`, `fix_table_data`, and `bbox`.
- Treat `content_list.json` as a read-only canonical parser artifact. Downstream
  phases may derive logical tables in memory, but they should not mutate and
  write back the canonical artifact.
- Re-trigger flows should update only the affected extraction rows for the
  target table set. Do not rewrite unrelated rows for the same task.
- Keep rule matching thresholds, status enums, and confidence inputs explicit in
  the schema or application layer. Do not bury critical business semantics in
  opaque JSON only.

---

## Migrations

- No migration tool is committed yet. Until one is added, `table-schema.md` is
  the canonical schema document and must be updated in the same change as any
  schema decision.
- When migrations are introduced, prefer forward-only changes and idempotent
  backfills.
- Split structural changes from data backfills when possible. This is important
  for large JSONB and vector indexes.
- Any schema PR must update all impacted artifacts together:
  - `table-schema.md`
  - API payload examples in `design.md`
  - any sample `rule.json` or `extracted_result.json` contracts

---

## Naming Conventions

- Use `snake_case` for table names, column names, indexes, and constraints.
- Keep the current `t_` prefix for business tables because it is already part of
  the documented schema (`t_task`, `t_document_toc`, `t_table_extraction_rule`,
  `t_extracted_result`).
- Keep index names descriptive and stable, for example `idx_t_result_task` or
  `idx_t_rule_vector`.
- Keep timestamp columns timezone-aware and suffix them with `_time`.
- Keep business status values explicit and uppercase, such as `QUEUED`,
  `PARSING`, `PARSED`, `FAILED`, `COMPLETED`, and `PENDING_REVIEW`.
- The current schema uses string flags such as `'0'` and `'1'` for some fields.
  Do not mix those with booleans ad hoc. If the project later migrates to proper
  booleans, do it systematically across schema, API, and frontend contracts.

---

## Examples

- `table-schema.md`: concrete table, column, and index naming rules.
- `design.md`: Phase 0 and Phase 5 show how task rows and extraction result rows
  evolve over time.
- `requirement.md`: sections 3.4 through 3.7 define business semantics that must
  survive persistence (`NOT_DISCLOSED`, `NOT_FIND`, unit normalization,
  confidence score, BBox traceability).

---

## Common Mistakes

- Storing raw PDFs or the full parser artifact in PostgreSQL instead of MinIO.
- Collapsing `null`, `NOT_DISCLOSED`, and `NOT_FIND` into one generic empty
  value.
- Mutating the canonical parser artifact rather than deriving a new logical
  representation for downstream phases.
- Hiding frequently queried fields inside `JSONB` when they need indexes or
  stable API contracts.
