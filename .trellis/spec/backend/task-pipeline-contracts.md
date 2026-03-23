# Task Pipeline Contracts

> Executable contracts for task submission, parser queue dispatch, and parser
> worker status writeback.

---

## Scenario: Extract Submission And Parser Lifecycle

### 1. Scope / Trigger

- Trigger: any change touching `POST /api/v1/extract`,
  `GET /api/v1/tasks/{task_id}`, `ParserTaskMessage`, MinIO object-key
  conventions, or parser worker status transitions.
- Primary files:
  - `apps/core_service/app/api/routes/tasks.py`
  - `apps/core_service/app/services/task_service.py`
  - `apps/core_service/app/schemas/tasks.py`
  - `apps/core_service/app/schemas/queue.py`
  - `apps/core_service/app/utils/object_storage.py`
  - `apps/parser_service/app/services/parser_worker.py`
  - `tests/core_service/test_tasks_api.py`
  - `tests/parser_service/test_worker.py`

### 2. Signatures

#### HTTP API

- `POST /api/v1/extract`
  - Content type: `multipart/form-data`
  - Fields:
    - `doc_type`: `ANNUAL_REPORT | IPO_PROSPECTUS | BOND_REPORT`
    - `file`: uploaded PDF bytes
- `GET /api/v1/tasks/{task_id}`
  - `task_id` path param is parsed as `int`
  - JSON response returns `task_id` as a decimal string

#### Queue Contract

- Model: `apps/core_service/app/schemas/queue.py::ParserTaskMessage`
- JSON payload fields:
  - `task_id: str`
  - `doc_type: DocumentType`
  - `file_name: str`
  - `file_hash: str`
  - `file_size: int`
  - `bucket: str`
  - `source_object_key: str`

#### Object Storage Contract

- Source PDF key:
  `tasks/{task_id}/source/{sanitized_file_name}`
- Parser artifact key:
  `tasks/{task_id}/content_list.json`
- Always build keys through:
  - `build_source_object_key(task_id, file_name)`
  - `build_content_list_object_key(task_id)`

#### Runtime Configuration

- `database_url`
- `redis_url`
- `parser_queue_name`
- `minio_endpoint`
- `minio_root_user`
- `minio_root_password`
- `minio_bucket`
- `task_id_node_id`
- `task_id_epoch_ms`

> Warning: `Settings.api_v1_prefix` exists, but current route strings are still
> declared explicitly in `apps/core_service/app/api/routes/tasks.py`. Changing
> the HTTP prefix requires updating routes, tests, and docs together.

### 3. Contracts

#### `POST /api/v1/extract` Request

| Field | Type | Required | Rules |
|------|------|----------|-------|
| `doc_type` | enum | yes | Must be one of `DocumentType` |
| `file` | upload | yes | Must include filename and non-empty bytes |

#### `POST /api/v1/extract` Success Response

- Response model: `TaskSubmissionResponse`
- Common fields:
  - `task_id: str`
  - `doc_type: DocumentType`
  - `file_name: str`
  - `file_hash: str`
  - `file_size: int`
  - `status: TaskStatus`
  - `remark: str | null`
  - `create_time: datetime`
  - `update_time: datetime`
  - `deduplicated: bool`
- Status-code rules:
  - `201 Created`: brand new task row persisted and dispatched
  - `200 OK`: duplicate upload reused an existing task

#### Dedup And Retry Rules

- Dedup fingerprint is the full tuple:
  - `(file_hash, file_size, doc_type)`
- Duplicate upload for a non-`FAILED` task:
  - returns existing task
  - `deduplicated = true`
  - touches `update_time`
  - must not upload source PDF again
  - must not publish a second queue message
- Duplicate upload for a `FAILED` task:
  - keeps the same `task_id`
  - uploads the source again
  - republishes the parser message
  - resets task state to `QUEUED`
  - clears `remark`

#### Task Lifecycle Contract

- Core service dispatch path:
  - persist task as `QUEUED`
  - upload source PDF to MinIO
  - publish `ParserTaskMessage` to `parser_queue`
- Parser worker path:
  - `QUEUED -> PARSING` before downloading the source PDF
  - `PARSING -> PARSED` only after `content_list.json` is uploaded
  - `PARSING -> FAILED` on source download failure, parse failure, or artifact
    upload failure

#### Stable Failure Remarks

- Source upload failure:
  - `Failed to store source PDF in object storage.`
- Queue publish failure:
  - `Failed to publish parser task message.`
- Source download failure:
  - `Failed to load source PDF from object storage.`
- Parse failure:
  - `Failed to parse source PDF.`
- Artifact upload failure:
  - `Failed to persist parser artifact to object storage.`

#### Error Envelope

- Model: `apps/core_service/app/schemas/errors.py::ErrorResponse`
- Fields:
  - `code: str`
  - `message: str`
  - `task_id: str | null`
  - `retryable: bool`
  - `details: dict[str, Any]`
  - `trace_id: str`

### 4. Validation & Error Matrix

| Boundary | Trigger | Code | HTTP | Retryable | Persisted task status | Notes |
|---------|---------|------|------|-----------|------------------------|-------|
| API upload | missing filename | `INVALID_FILE_UPLOAD` | `400` | no | none | request rejected before dispatch |
| API upload | empty file bytes | `INVALID_FILE_UPLOAD` | `400` | no | none | request rejected before dispatch |
| API read | missing task id in DB | `TASK_NOT_FOUND` | `404` | no | unchanged | fetch path only |
| DB | create/read/update failure | `DATABASE_UNAVAILABLE` | `503` | yes | unchanged or unknown | include DB exception name in `details.reason` when available |
| MinIO upload | source PDF upload failed | `OBJECT_STORAGE_UNAVAILABLE` | `503` | yes | `FAILED` | `task_id` must be returned |
| Redis publish | parser message publish failed | `QUEUE_UNAVAILABLE` | `503` | yes | `FAILED` | `task_id` must be returned |
| Queue consume | invalid parser payload | `QUEUE_PAYLOAD_INVALID` | n/a | no | unchanged | worker logs and discards payload |
| MinIO download | source PDF missing/download failed | `OBJECT_STORAGE_UNAVAILABLE` | n/a | n/a | `FAILED` | worker remark must be stable |
| Parser engine | parse rejected or invalid source | `PARSE_FAILED` | n/a | n/a | `FAILED` | worker remark must be stable |
| MinIO upload | artifact upload failed | `OBJECT_STORAGE_UNAVAILABLE` | n/a | n/a | `FAILED` | worker remark must be stable |

### 5. Good / Base / Bad Cases

#### Good

- Fresh upload to `POST /api/v1/extract`
  - returns `201`
  - response `status` is `QUEUED`
  - MinIO contains `tasks/{task_id}/source/{file_name}`
  - queue contains one `ParserTaskMessage`
  - parser worker eventually writes `tasks/{task_id}/content_list.json`
  - `GET /api/v1/tasks/{task_id}` returns `PARSED`

#### Base

- Duplicate upload of the same file and `doc_type`
  - returns `200`
  - `deduplicated = true`
  - `task_id` stays unchanged
  - no second source upload
  - no second queue message

- Duplicate upload of a previously `FAILED` task
  - returns `200`
  - `deduplicated = true`
  - same `task_id` is re-used
  - source upload and queue publish happen again
  - status is restored to `QUEUED`

#### Bad

- Empty upload must fail with `400 INVALID_FILE_UPLOAD`
- Source upload or queue publish outage must fail with `503` and preserve
  `task_id`
- Invalid queue payload must not crash the worker loop
- Non-PDF or invalid parser input must end in task status `FAILED`

### 6. Tests Required

- Command:
  - `.\.venv\Scripts\python.exe -m ruff check apps alembic tests main.py`
  - `.\.venv\Scripts\python.exe -m pytest -q`
- Required API assertions in `tests/core_service/test_tasks_api.py`:
  - fresh upload returns `201`
  - status fetch uses `/api/v1/tasks/{task_id}`
  - duplicate upload does not create extra upload or queue message
  - failed dispatch marks task `FAILED`
  - failed duplicate re-dispatch reuses the same `task_id`
  - missing task returns `404 TASK_NOT_FOUND`
- Required parser assertions in `tests/parser_service/test_worker.py`:
  - worker flips `QUEUED -> PARSING -> PARSED`
  - successful parse uploads `content_list.json`
  - parse error marks task `FAILED`
  - source download failure marks task `FAILED`

### 7. Wrong vs Correct

#### Wrong

- Use `/api/v1/extract` for submission but `/tasks/{task_id}` for status fetch.
- Construct MinIO keys inline in multiple services.
- Return numeric `task_id` values in JSON and let JavaScript lose precision.
- Re-dispatch a `FAILED` task by creating a brand new task row.

#### Correct

- Keep both task endpoints under `/api/v1/*`.
- Build MinIO keys only through the shared helper functions.
- Return `task_id` as a decimal string in HTTP and queue payloads.
- Re-use the existing `task_id` when retrying a previously failed duplicate.
