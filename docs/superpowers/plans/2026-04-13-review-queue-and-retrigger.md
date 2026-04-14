# Review Queue And Targeted Retrigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 `PENDING_REVIEW` 后端闭环，提供 review queue/result API、人工修复写回，以及针对指定表格的局部重提取能力。

**Architecture:** 不新增 review 专用数据库表，而是直接复用 `t_task.status` 和 `t_extracted_result.needs_review/fix_table_data` 形成 review queue 视图。局部重跑复用现有 extractor 主链路：新增 `reextract_queue` 和带 `target_table_codes` 的 `ExtractorTaskMessage`，Extractor Worker 提供统一 `process_message(...)`，普通抽取和重提取仅在“消费哪个队列、处理哪些规则”上有差异。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, Redis, Pydantic v2, pytest

---

## File Structure

- Create: `apps/core_service/app/schemas/review.py`
- Create: `apps/core_service/app/services/review_service.py`
- Create: `apps/core_service/app/services/retrigger_service.py`
- Modify: `apps/core_service/app/repositories/task_repository.py`
- Modify: `apps/core_service/app/repositories/extracted_result_repository.py`
- Modify: `apps/core_service/app/schemas/queue.py`
- Modify: `apps/core_service/app/clients/queue.py`
- Modify: `apps/core_service/app/settings.py`
- Modify: `apps/core_service/app/api/dependencies.py`
- Create: `apps/core_service/app/api/routes/review.py`
- Modify: `apps/core_service/app/api/router.py`
- Modify: `apps/core_service/app/services/extractor_worker.py`
- Modify: `apps/core_service/app/extractor_main.py`
- Modify: `tests/conftest.py`
- Create: `tests/core_service/test_review_service.py`
- Create: `tests/core_service/test_review_routes.py`
- Modify: `tests/core_service/test_extractor_worker.py`

## Preflight

- [ ] **Step 1: Verify the current review baseline**

Run: `.venv/bin/python -m pytest tests/core_service/test_extractor_worker.py tests/core_service/test_extraction_repositories.py -q`
Expected: PASS

- [ ] **Step 2: Verify the task API baseline**

Run: `.venv/bin/python -m pytest tests/parser_service/test_worker.py tests/core_service/test_extractor_worker.py -q`
Expected: PASS

### Task 1: Add Review Query Schemas, Repository Methods, And Service

**Files:**
- Create: `apps/core_service/app/schemas/review.py`
- Create: `apps/core_service/app/services/review_service.py`
- Modify: `apps/core_service/app/repositories/task_repository.py`
- Modify: `apps/core_service/app/repositories/extracted_result_repository.py`
- Create: `tests/core_service/test_review_service.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing review service tests**

```python
from decimal import Decimal

from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.task import Task
from apps.core_service.app.services.review_service import ReviewService
from apps.shared.enums.task_status import TaskStatus


async def test_review_service_lists_pending_review_tasks(test_app) -> None:
    task = Task(
        id=1001,
        doc_type="ANNUAL_REPORT",
        file_name="annual.pdf",
        file_hash="hash-1",
        file_size=128,
        status=TaskStatus.PENDING_REVIEW,
        remark=None,
    )
    await test_app.state.task_repository.create(None, task)
    test_app.state.result_repository.rows.append(
        ExtractedResult(
            id=2001,
            task_id=1001,
            rule_id=3001,
            target_table_code="main_business_revenue",
            unit="CNY_TEN_THOUSAND",
            currency="CNY",
            extraction_route="SLOW_TRACK",
            data_status="SUCCESS",
            table_data={"headers": ["分部", "收入"], "rows": [["境内", "100"]]},
            fix_table_data=None,
            start_page=3,
            end_page=3,
            bbox=None,
            confidence_score=Decimal("75.00"),
            needs_review="1",
            remark="Missing unit in source table.",
        )
    )

    service = ReviewService(
        session=test_app.state.database_client.session_factory(),
        task_repository=test_app.state.task_repository,
        result_repository=test_app.state.result_repository,
    )

    queue = await service.list_pending_review_tasks()

    assert len(queue) == 1
    assert queue[0].task_id == "1001"
    assert queue[0].pending_result_count == 1
    assert queue[0].target_table_codes == ["main_business_revenue"]
```

```python
async def test_review_service_returns_task_results(test_app) -> None:
    service = ReviewService(
        session=test_app.state.database_client.session_factory(),
        task_repository=test_app.state.task_repository,
        result_repository=test_app.state.result_repository,
    )

    results = await service.get_task_results(task_id=1001)

    assert results[0].result_id == "2001"
    assert results[0].needs_review == "1"
    assert results[0].fix_table_data is None
```

- [ ] **Step 2: Run the review service tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.services.review_service'`

- [ ] **Step 3: Implement review schemas, repository methods, and service**

```python
from datetime import datetime

from pydantic import BaseModel


class ReviewQueueItem(BaseModel):
    task_id: str
    doc_type: str
    file_name: str
    update_time: datetime
    pending_result_count: int
    target_table_codes: list[str]


class ExtractedResultRead(BaseModel):
    result_id: str
    target_table_code: str
    data_status: str
    extraction_route: str | None = None
    confidence_score: str
    needs_review: str
    table_data: dict[str, object] | None = None
    fix_table_data: dict[str, object] | None = None
    remark: str | None = None


class ResultFixRequest(BaseModel):
    fix_table_data: dict[str, object]
    remark: str | None = None
```

```python
class ReviewService:
    def __init__(self, *, session, task_repository, result_repository) -> None:
        self._session = session
        self._task_repository = task_repository
        self._result_repository = result_repository

    async def list_pending_review_tasks(self) -> list[ReviewQueueItem]:
        tasks = await self._task_repository.list_pending_review_tasks(self._session)
        queue: list[ReviewQueueItem] = []
        for task in tasks:
            pending_rows = await self._result_repository.list_pending_review_rows(
                self._session,
                task_id=task.id,
            )
            queue.append(
                ReviewQueueItem(
                    task_id=str(task.id),
                    doc_type=task.doc_type,
                    file_name=task.file_name,
                    update_time=task.update_time,
                    pending_result_count=len(pending_rows),
                    target_table_codes=[row.target_table_code for row in pending_rows],
                )
            )
        return queue

    async def get_task_results(self, *, task_id: int) -> list[ExtractedResultRead]:
        rows = await self._result_repository.list_by_task(self._session, task_id=task_id)
        return [
            ExtractedResultRead(
                result_id=str(row.id),
                target_table_code=row.target_table_code,
                data_status=row.data_status,
                extraction_route=row.extraction_route,
                confidence_score=str(row.confidence_score),
                needs_review=row.needs_review,
                table_data=row.table_data,
                fix_table_data=row.fix_table_data,
                remark=row.remark,
            )
            for row in rows
        ]
```

- [ ] **Step 4: Run the review service suite**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit the review service foundation**

```bash
git add apps/core_service/app/schemas/review.py apps/core_service/app/services/review_service.py apps/core_service/app/repositories/task_repository.py apps/core_service/app/repositories/extracted_result_repository.py tests/core_service/test_review_service.py tests/conftest.py
git commit -m "feat(review): 新增待复核查询服务"
```

### Task 2: Expose Review Queue And Result Read APIs

**Files:**
- Create: `apps/core_service/app/api/routes/review.py`
- Modify: `apps/core_service/app/api/dependencies.py`
- Modify: `apps/core_service/app/api/router.py`
- Create: `tests/core_service/test_review_routes.py`

- [ ] **Step 1: Write the failing review route tests**

```python
from decimal import Decimal

from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.task import Task
from apps.shared.enums.task_status import TaskStatus


async def _seed_review_state(test_app) -> None:
    task = Task(
        id=1001,
        doc_type="ANNUAL_REPORT",
        file_name="annual.pdf",
        file_hash="hash-1",
        file_size=128,
        status=TaskStatus.PENDING_REVIEW,
        remark=None,
    )
    await test_app.state.task_repository.create(None, task)
    test_app.state.result_repository.rows.append(
        ExtractedResult(
            id=2001,
            task_id=1001,
            rule_id=3001,
            target_table_code="main_business_revenue",
            unit="CNY_TEN_THOUSAND",
            currency="CNY",
            extraction_route="SLOW_TRACK",
            data_status="SUCCESS",
            table_data={"headers": ["分部", "收入"], "rows": [["境内", "100"]]},
            fix_table_data=None,
            start_page=3,
            end_page=3,
            bbox=None,
            confidence_score=Decimal("75.00"),
            needs_review="1",
            remark="Missing unit in source table.",
        )
    )


async def test_get_review_queue(async_client, test_app) -> None:
    await _seed_review_state(test_app)

    response = await async_client.get("/api/v1/review/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == "1001"
    assert payload[0]["pending_result_count"] == 1


async def test_get_task_results(async_client, test_app) -> None:
    await _seed_review_state(test_app)

    response = await async_client.get("/api/v1/tasks/1001/results")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["result_id"] == "2001"
    assert payload[0]["target_table_code"] == "main_business_revenue"
```

- [ ] **Step 2: Run the review route tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_routes.py -q`
Expected: FAIL with `404 Not Found`

- [ ] **Step 3: Implement the review routes and dependencies**

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from apps.core_service.app.api.dependencies import get_review_service
from apps.core_service.app.schemas.review import ExtractedResultRead, ReviewQueueItem
from apps.core_service.app.services.review_service import ReviewService

router = APIRouter(tags=["review"])
ReviewServiceDependency = Annotated[ReviewService, Depends(get_review_service)]


@router.get("/api/v1/review/tasks", response_model=list[ReviewQueueItem])
async def list_review_tasks(service: ReviewServiceDependency) -> list[ReviewQueueItem]:
    return await service.list_pending_review_tasks()


@router.get("/api/v1/tasks/{task_id}/results", response_model=list[ExtractedResultRead])
async def get_task_results(task_id: int, service: ReviewServiceDependency) -> list[ExtractedResultRead]:
    return await service.get_task_results(task_id=task_id)
```

```python
from apps.core_service.app.services.review_service import ReviewService


async def get_review_service(request: Request, session: SessionDependency) -> ReviewService:
    return ReviewService(
        session=session,
        task_repository=getattr(request.app.state, "task_repository", None),
        result_repository=getattr(request.app.state, "result_repository", None),
    )
```

- [ ] **Step 4: Run the review route suite**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_routes.py tests/core_service/test_review_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit the review APIs**

```bash
git add apps/core_service/app/api/routes/review.py apps/core_service/app/api/dependencies.py apps/core_service/app/api/router.py tests/core_service/test_review_routes.py
git commit -m "feat(review): 暴露待复核查询接口"
```

### Task 3: Add Manual Fix Writeback And Task Status Recompute

**Files:**
- Modify: `apps/core_service/app/services/review_service.py`
- Modify: `apps/core_service/app/repositories/extracted_result_repository.py`
- Modify: `apps/core_service/app/repositories/task_repository.py`
- Modify: `apps/core_service/app/api/routes/review.py`
- Modify: `tests/core_service/test_review_service.py`
- Modify: `tests/core_service/test_review_routes.py`

- [ ] **Step 1: Write the failing manual fix tests**

```python
async def test_review_service_applies_fix_and_clears_task_review_flag(test_app) -> None:
    service = ReviewService(
        session=test_app.state.database_client.session_factory(),
        task_repository=test_app.state.task_repository,
        result_repository=test_app.state.result_repository,
    )

    updated = await service.apply_fix(
        task_id=1001,
        result_id=2001,
        fix_table_data={"headers": ["分部", "收入"], "rows": [["境内", "100.00"]]},
        remark="人工复核确认收入口径。",
    )

    assert updated.fix_table_data == {"headers": ["分部", "收入"], "rows": [["境内", "100.00"]]}
    assert updated.needs_review == "0"
    task = await test_app.state.task_repository.get_by_id(None, 1001)
    assert task.status == "COMPLETED"
```

```python
async def test_patch_result_fix(async_client, test_app) -> None:
    await _seed_review_state(test_app)

    response = await async_client.patch(
        "/api/v1/tasks/1001/results/2001",
        json={
            "fix_table_data": {"headers": ["分部", "收入"], "rows": [["境内", "100.00"]]},
            "remark": "人工复核确认收入口径。",
        },
    )

    assert response.status_code == 200
    assert response.json()["needs_review"] == "0"
    assert response.json()["fix_table_data"]["rows"] == [["境内", "100.00"]]
```

- [ ] **Step 2: Run the manual fix tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_service.py tests/core_service/test_review_routes.py -q`
Expected: FAIL because neither the service nor PATCH route exists

- [ ] **Step 3: Implement fix writeback and status recompute**

```python
async def apply_fix(self, *, task_id: int, result_id: int, fix_table_data: dict[str, object], remark: str | None) -> ExtractedResultRead:
    row = await self._result_repository.apply_fix(
        self._session,
        task_id=task_id,
        result_id=result_id,
        fix_table_data=fix_table_data,
        remark=remark,
    )
    pending_count = await self._result_repository.count_pending_review_by_task(
        self._session,
        task_id=task_id,
    )
    task = await self._task_repository.get_by_id(self._session, task_id)
    if task is not None:
        await self._task_repository.set_status(
            self._session,
            task,
            status="PENDING_REVIEW" if pending_count else "COMPLETED",
            remark=None,
        )
        await self._session.commit()
    return ExtractedResultRead(
        result_id=str(row.id),
        target_table_code=row.target_table_code,
        data_status=row.data_status,
        extraction_route=row.extraction_route,
        confidence_score=str(row.confidence_score),
        needs_review=row.needs_review,
        table_data=row.table_data,
        fix_table_data=row.fix_table_data,
        remark=row.remark,
    )
```

```python
@router.patch("/api/v1/tasks/{task_id}/results/{result_id}", response_model=ExtractedResultRead)
async def patch_result_fix(
    task_id: int,
    result_id: int,
    request: ResultFixRequest,
    service: ReviewServiceDependency,
) -> ExtractedResultRead:
    return await service.apply_fix(
        task_id=task_id,
        result_id=result_id,
        fix_table_data=request.fix_table_data,
        remark=request.remark,
    )
```

- [ ] **Step 4: Run the manual fix suite**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_service.py tests/core_service/test_review_routes.py -q`
Expected: PASS

- [ ] **Step 5: Commit the manual review writeback flow**

```bash
git add apps/core_service/app/services/review_service.py apps/core_service/app/repositories/extracted_result_repository.py apps/core_service/app/repositories/task_repository.py apps/core_service/app/api/routes/review.py tests/core_service/test_review_service.py tests/core_service/test_review_routes.py
git commit -m "feat(review): 支持人工修复写回"
```

### Task 4: Add Reextract Queue Contract And Targeted Worker Processing

**Files:**
- Modify: `apps/core_service/app/schemas/queue.py`
- Modify: `apps/core_service/app/clients/queue.py`
- Modify: `apps/core_service/app/settings.py`
- Modify: `apps/core_service/app/services/extractor_worker.py`
- Modify: `apps/core_service/app/extractor_main.py`
- Modify: `tests/conftest.py`
- Modify: `tests/core_service/test_extractor_worker.py`

- [ ] **Step 1: Write the failing targeted reextract worker test**

```python
async def test_extractor_worker_reextracts_only_selected_target_tables(test_app) -> None:
    message = ExtractorTaskMessage(
        task_id="1001",
        doc_type="ANNUAL_REPORT",
        bucket=test_app.state.object_storage_client.bucket_name,
        content_list_object_key="tasks/1001/content_list.json",
        target_table_codes=["main_business_revenue"],
    )
    test_app.state.queue_client.reextract_messages.append(message)

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_reextract_message(timeout_seconds=0) is True

    rows = [row for row in test_app.state.result_repository.rows if row.task_id == 1001]
    assert [row.target_table_code for row in rows] == ["main_business_revenue"]
```

- [ ] **Step 2: Run the targeted worker test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core_service/test_extractor_worker.py::test_extractor_worker_reextracts_only_selected_target_tables -q`
Expected: FAIL because `target_table_codes` and `reextract_messages` do not exist

- [ ] **Step 3: Implement queue contract and worker processing**

```python
class ExtractorTaskMessage(BaseModel):
    task_id: str
    doc_type: DocumentType
    bucket: str
    content_list_object_key: str
    target_table_codes: list[str] | None = None
```

```python
class QueueClient:
    queue_name: str
    extractor_queue_name: str | None = None
    reextract_queue_name: str | None = None

    async def publish_reextract_task(self, message: ExtractorTaskMessage) -> None:
        raise NotImplementedError

    async def consume_reextract_task(self, *, timeout_seconds: int) -> ExtractorTaskMessage | None:
        raise NotImplementedError
```

```python
class ExtractorWorker:
    async def process_next_message(self, *, timeout_seconds: int) -> bool:
        message = await self._queue_client.consume_extractor_task(timeout_seconds=timeout_seconds)
        if message is None:
            return False
        return await self.process_message(message)

    async def process_next_reextract_message(self, *, timeout_seconds: int) -> bool:
        message = await self._queue_client.consume_reextract_task(timeout_seconds=timeout_seconds)
        if message is None:
            return False
        return await self.process_message(message)

    async def process_message(self, message: ExtractorTaskMessage) -> bool:
        selected_codes = set(message.target_table_codes or [])
        artifact_bytes = await self._object_storage_client.download_bytes(
            bucket=message.bucket,
            object_key=message.content_list_object_key,
        )
        content_blocks = load_content_list(artifact_bytes)
        logical_tables = self._logical_table_builder.build(content_blocks)
        async with self._session_factory() as session:
            task = await self._task_repository.get_by_id(session, int(message.task_id))
            if task is None:
                return True
            rules = await self._rule_repository.list_active_by_doc_type(session, doc_type=message.doc_type)
            selected_rules = [
                rule
                for rule in rules
                if not selected_codes or rule.target_table_code in selected_codes
            ]
            final_outcomes: list[ExtractionOutcome] = []
        for rule in selected_rules:
            decision = await self._table_router.route(
                rule=rule,
                toc_nodes=[],
                logical_tables=logical_tables,
                content_blocks=content_blocks,
            )
            outcome = await self._build_outcome(rule=rule, decision=decision)
            outcome = self._extraction_normalizer.normalize(
                outcome=outcome,
                decision=decision,
                content_blocks=content_blocks,
            )
            outcome = self._confidence_scorer.apply(outcome=outcome)
            final_outcomes.append(outcome)
            await self._result_repository.upsert_result(
                session,
                result_id=self._id_generator.next_id(),
                task_id=task.id,
                rule=rule,
                outcome=outcome,
            )
        pending_count = await self._result_repository.count_pending_review_by_task(session, task_id=task.id)
        await self._task_repository.set_status(
            session,
            task,
            status="PENDING_REVIEW" if pending_count else "COMPLETED",
            remark=None if selected_rules else "No active extraction rules configured.",
        )
        await session.commit()
        return True
```

```python
while True:
    if await worker.process_next_reextract_message(timeout_seconds=0):
        continue
    await worker.process_next_message(timeout_seconds=5)
```

- [ ] **Step 4: Run the extractor worker reextract suite**

Run: `.venv/bin/python -m pytest tests/core_service/test_extractor_worker.py -q`
Expected: PASS

- [ ] **Step 5: Commit targeted reextract processing**

```bash
git add apps/core_service/app/schemas/queue.py apps/core_service/app/clients/queue.py apps/core_service/app/settings.py apps/core_service/app/services/extractor_worker.py apps/core_service/app/extractor_main.py tests/conftest.py tests/core_service/test_extractor_worker.py
git commit -m "feat(review): 支持局部重提取队列"
```

### Task 5: Add Retrigger API And Service

**Files:**
- Create: `apps/core_service/app/services/retrigger_service.py`
- Modify: `apps/core_service/app/api/dependencies.py`
- Modify: `apps/core_service/app/api/routes/review.py`
- Modify: `tests/core_service/test_review_routes.py`

- [ ] **Step 1: Write the failing retrigger route test**

```python
from apps.core_service.app.db.models.task import Task


async def test_post_retrigger_enqueues_selected_target_tables(async_client, test_app) -> None:
    task = Task(
        id=1001,
        doc_type="ANNUAL_REPORT",
        file_name="annual.pdf",
        file_hash="hash-1",
        file_size=128,
        status="COMPLETED",
        remark=None,
    )
    await test_app.state.task_repository.create(None, task)

    response = await async_client.post(
        "/api/v1/extract/retrigger",
        json={
            "task_id": "1001",
            "target_table_codes": ["main_business_revenue"],
        },
    )

    assert response.status_code == 202
    assert len(test_app.state.queue_client.reextract_messages) == 1
    message = test_app.state.queue_client.reextract_messages[0]
    assert message.task_id == "1001"
    assert message.target_table_codes == ["main_business_revenue"]
```

- [ ] **Step 2: Run the retrigger route test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_routes.py::test_post_retrigger_enqueues_selected_target_tables -q`
Expected: FAIL with `404 Not Found`

- [ ] **Step 3: Implement the retrigger service and route**

```python
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, Field

from apps.core_service.app.api.dependencies import get_retrigger_service
from apps.core_service.app.schemas.queue import ExtractorTaskMessage
from apps.core_service.app.utils.object_storage import build_content_list_object_key


class RetriggerRequest(BaseModel):
    task_id: str
    target_table_codes: list[str] = Field(min_length=1)


class RetriggerResponse(BaseModel):
    task_id: str
    accepted: bool
    target_table_codes: list[str]


class RetriggerService:
    def __init__(self, *, session, task_repository, queue_client, bucket_name: str) -> None:
        self._session = session
        self._task_repository = task_repository
        self._queue_client = queue_client
        self._bucket_name = bucket_name

    async def retrigger(self, *, task_id: int, target_table_codes: list[str]) -> RetriggerResponse:
        task = await self._task_repository.get_by_id(self._session, task_id)
        if task is None:
            raise AppError(
                code="TASK_NOT_FOUND",
                message=f"Task {task_id} was not found.",
                status_code=404,
                task_id=task_id,
            )

        message = ExtractorTaskMessage(
            task_id=str(task.id),
            doc_type=task.doc_type,
            bucket=self._bucket_name,
            content_list_object_key=build_content_list_object_key(task.id),
            target_table_codes=target_table_codes,
        )
        await self._queue_client.publish_reextract_task(message)
        return RetriggerResponse(
            task_id=str(task.id),
            accepted=True,
            target_table_codes=target_table_codes,
        )
```

```python
RetriggerServiceDependency = Annotated[RetriggerService, Depends(get_retrigger_service)]


@router.post("/api/v1/extract/retrigger", response_model=RetriggerResponse, status_code=202)
async def post_retrigger(request: RetriggerRequest, service: RetriggerServiceDependency) -> RetriggerResponse:
    return await service.retrigger(
        task_id=int(request.task_id),
        target_table_codes=request.target_table_codes,
    )
```

```python
async def get_retrigger_service(request: Request, session: SessionDependency) -> RetriggerService:
    return RetriggerService(
        session=session,
        task_repository=getattr(request.app.state, "task_repository", None),
        queue_client=request.app.state.queue_client,
        bucket_name=request.app.state.object_storage_client.bucket_name,
    )
```

- [ ] **Step 4: Run the review + retrigger route suite**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_routes.py tests/core_service/test_extractor_worker.py -q`
Expected: PASS

- [ ] **Step 5: Commit the retrigger API**

```bash
git add apps/core_service/app/services/retrigger_service.py apps/core_service/app/api/dependencies.py apps/core_service/app/api/routes/review.py tests/core_service/test_review_routes.py
git commit -m "feat(review): 暴露局部重提取接口"
```

## Final Verification

- [ ] **Step 1: Run the review/retrigger focused suite**

Run: `.venv/bin/python -m pytest tests/core_service/test_review_service.py tests/core_service/test_review_routes.py tests/core_service/test_extractor_worker.py -q`
Expected: PASS

- [ ] **Step 2: Run the full repository suite**

Run: `.venv/bin/python -m pytest tests -q`
Expected: PASS

## Assumptions

- review queue 直接用现有数据构造，不新增 `t_review_queue`；筛选条件是 `t_task.status='PENDING_REVIEW'` 且存在 `needs_review='1'` 的结果行。
- retrigger API 使用 `target_table_codes` 而不是文档里的 `TargetTableIDs`，因为当前仓库已经以 `target_table_code` 作为业务主键；若后续引入规则管理后台，再把 request shape 扩展为同时支持 rule id。
- `content_list.json` 仍按固定对象存储路径 `tasks/{task_id}/content_list.json` 读取，retrigger 不会重新跑 parser，也不会重传源 PDF。
