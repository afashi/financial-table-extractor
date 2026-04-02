# Extraction Backbone Catch-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前只到 `PARSED` 的解析链路补成一个可运行的 extraction backbone：parser 成功后继续投递 extractor 队列，extractor worker 读取 `content_list.json`、加载激活规则、写入占位结果，并将任务推进到 `COMPLETED` 终态。

**Architecture:** 保持现有 `core_service -> parser_queue -> parser_service` 链路不变，在 parser 成功落盘 `content_list.json` 后追加第二跳 `parser_service -> extractor_queue -> core extractor worker`。本计划只实现“骨架链路”和持久化契约，不实现跨页合并、语义路由、LLM fallback、单位归一化、置信度评分或前端溯源。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic, Redis, MinIO, Pydantic v2, pytest

---

## Requirement And Design Comparison

已对齐的部分：

- `Phase 0` 任务接入、文件指纹去重、源 PDF 上传、`parser_queue` 投递已经落地。
- `Phase 1` parser worker 已能消费队列、生成最小合法 `content_list.json`、上传 MinIO，并完成 `QUEUED -> PARSING -> PARSED|FAILED` 状态流转。
- `.venv/bin/pytest -q` 当前实测通过，基线为 `10 passed`。

尚未落地的部分：

- `Phase 2` 之后的 extraction 下游完全缺失：没有 `extractor_queue`、没有 extractor worker、没有规则表、没有结果表、没有终态落盘。
- `requirement.md` / `design.md` 中的跨页长表合并、目录树构建、路径指纹粗排、锚点精排、LLM fallback、单位归一化、置信度评分、traceability backend / UI 都还没开始。
- parser 仍是 skeleton engine，不是 MinerU 真解析；当前 `content_list.json` 是占位产物，不包含真实表格结构。

设计与现状的显著偏差：

- 设计稿写的是 `Celery + Redis`，当前实现是自定义 `RedisQueueClient`；本计划不切换消息框架，先沿用现有抽象补完骨架。
- 设计稿写了 `pgvector` / `semantic_vector` / `Vue traceability UI`，当前仓库还没有任何相关代码；这些内容拆到后续计划。

## Scope Check

`requirement.md` 覆盖了多个相对独立的子系统，不能继续堆在一个计划里一起做。当前仓库最缺的是“解析后无下游”的主链路断点，所以本计划只处理 `Extraction Backbone`。后续按下面顺序拆分：

1. `Pagination Merge And Logical Table Builder`
2. `Semantic Routing, Fast Track, And LLM Fallback`
3. `Normalization And Confidence Scoring`
4. `Traceability Delivery, Review Queue, And Retrigger API`

## File Structure

本计划只创建或修改下面这些文件：

- Modify: `apps/core_service/app/schemas/queue.py`
  增加 `ExtractorTaskMessage`。
- Modify: `apps/core_service/app/clients/queue.py`
  在现有 Redis 客户端上补 extractor publish / consume。
- Modify: `apps/core_service/app/settings.py`
  增加 `extractor_queue_name`。
- Modify: `apps/parser_service/app/settings.py`
  增加 `extractor_queue_name`。
- Modify: `apps/parser_service/app/services/parser_worker.py`
  parser 成功后发布 extractor 消息；下游队列投递失败时写失败状态。
- Modify: `apps/parser_service/app/main.py`
  初始化同时支持 parser / extractor 队列名的 Redis 客户端。
- Modify: `apps/core_service/app/db/models/__init__.py`
  导出新模型。
- Create: `apps/core_service/app/db/models/table_extraction_rule.py`
  保存激活规则元数据。
- Create: `apps/core_service/app/db/models/extracted_result.py`
  保存每条规则对应的 extraction 结果。
- Create: `apps/core_service/app/repositories/table_extraction_rule_repository.py`
  按 `doc_type` 读取激活规则。
- Create: `apps/core_service/app/repositories/extracted_result_repository.py`
  Upsert 占位 `NOT_FIND` 结果。
- Create: `apps/core_service/app/services/extractor_worker.py`
  消费 `ExtractorTaskMessage`、读取 artifact、写结果、更新终态。
- Create: `apps/core_service/app/extractor_main.py`
  extractor worker 可执行入口。
- Modify: `pyproject.toml`
  注册 extractor worker CLI。
- Create: `alembic/versions/20260401_0002_add_extraction_tables.py`
  创建 `t_table_extraction_rule`、`t_extracted_result`。
- Modify: `tests/conftest.py`
  扩展 fake queue / fake rule repo / fake result repo。
- Modify: `tests/parser_service/test_worker.py`
  覆盖 parser 发布 extractor 消息。
- Create: `tests/core_service/test_extraction_repositories.py`
  覆盖规则读取和结果 upsert。
- Create: `tests/core_service/test_extractor_worker.py`
  覆盖 extractor worker 完整骨架链路。

## Preflight

在执行 Task 2 之前，先确保本地依赖服务已启动：

```bash
docker compose up -d postgres redis minio
```

预期：

- `financial-table-extractor-postgres`、`financial-table-extractor-redis`、`financial-table-extractor-minio` 进入运行态。

### Task 1: Add Extractor Queue Contract And Parser Handoff

**Files:**
- Modify: `apps/core_service/app/schemas/queue.py`
- Modify: `apps/core_service/app/clients/queue.py`
- Modify: `apps/core_service/app/settings.py`
- Modify: `apps/parser_service/app/settings.py`
- Modify: `apps/parser_service/app/services/parser_worker.py`
- Modify: `apps/parser_service/app/main.py`
- Modify: `tests/conftest.py`
- Modify: `tests/parser_service/test_worker.py`

- [ ] **Step 1: Write the failing parser handoff test**

```python
# tests/parser_service/test_worker.py
async def test_parser_worker_emits_extractor_message(async_client, test_app) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("handoff.pdf", b"%PDF-1.7\nhandoff", "application/pdf")},
    )
    payload = response.json()

    worker = build_worker(test_app, SkeletonParserEngine())
    assert await worker.process_next_message(timeout_seconds=0) is True

    extractor_messages = test_app.state.queue_client.extractor_messages
    assert len(extractor_messages) == 1

    message = extractor_messages[0]
    assert message.task_id == payload["task_id"]
    assert message.doc_type == "ANNUAL_REPORT"
    assert message.bucket == test_app.state.object_storage_client.bucket_name
    assert message.content_list_object_key == build_content_list_object_key(int(payload["task_id"]))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/parser_service/test_worker.py::test_parser_worker_emits_extractor_message -q`

Expected: FAIL with `AttributeError` because `FakeQueueClient` does not expose `extractor_messages`, or because `ParserWorker` never publishes extractor messages.

- [ ] **Step 3: Implement extractor message schema, dual-queue client support, and parser handoff**

```python
# apps/core_service/app/schemas/queue.py
from pydantic import BaseModel

from apps.shared.enums.doc_type import DocumentType


class ParserTaskMessage(BaseModel):
    task_id: str
    doc_type: DocumentType
    file_name: str
    file_hash: str
    file_size: int
    bucket: str
    source_object_key: str


class ExtractorTaskMessage(BaseModel):
    task_id: str
    doc_type: DocumentType
    bucket: str
    content_list_object_key: str
```

```python
# apps/core_service/app/clients/queue.py
import json

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from apps.core_service.app.errors import QueueClientError, QueuePayloadError
from apps.core_service.app.schemas.queue import ExtractorTaskMessage, ParserTaskMessage


class QueueClient:
    queue_name: str
    extractor_queue_name: str | None = None

    async def healthcheck(self) -> None:
        return None

    async def publish_parser_task(self, message: ParserTaskMessage) -> None:
        raise NotImplementedError

    async def consume_parser_task(self, *, timeout_seconds: int) -> ParserTaskMessage | None:
        raise NotImplementedError

    async def publish_extractor_task(self, message: ExtractorTaskMessage) -> None:
        raise NotImplementedError

    async def consume_extractor_task(self, *, timeout_seconds: int) -> ExtractorTaskMessage | None:
        raise NotImplementedError

    async def dispose(self) -> None:
        return None


class RedisQueueClient(QueueClient):
    def __init__(
        self,
        *,
        redis_url: str,
        queue_name: str,
        extractor_queue_name: str | None = None,
    ) -> None:
        self.queue_name = queue_name
        self.extractor_queue_name = extractor_queue_name
        self._redis = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def healthcheck(self) -> None:
        try:
            await self._redis.ping()
        except RedisError as exc:
            raise QueueClientError(
                f"Failed to connect to Redis queue '{self.queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def publish_parser_task(self, message: ParserTaskMessage) -> None:
        await self._push(self.queue_name, message.model_dump(mode="json"))

    async def consume_parser_task(self, *, timeout_seconds: int) -> ParserTaskMessage | None:
        payload = await self._pop(self.queue_name, timeout_seconds=timeout_seconds)
        if payload is None:
            return None
        try:
            return ParserTaskMessage.model_validate_json(payload)
        except ValidationError as exc:
            raise QueuePayloadError(
                f"Invalid payload was received from Redis queue '{self.queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def publish_extractor_task(self, message: ExtractorTaskMessage) -> None:
        target_queue = self._require_extractor_queue_name()
        await self._push(target_queue, message.model_dump(mode="json"))

    async def consume_extractor_task(self, *, timeout_seconds: int) -> ExtractorTaskMessage | None:
        target_queue = self._require_extractor_queue_name()
        payload = await self._pop(target_queue, timeout_seconds=timeout_seconds)
        if payload is None:
            return None
        try:
            return ExtractorTaskMessage.model_validate_json(payload)
        except ValidationError as exc:
            raise QueuePayloadError(
                f"Invalid payload was received from Redis queue '{target_queue}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def _push(self, queue_name: str, payload: dict[str, object]) -> None:
        try:
            await self._redis.rpush(queue_name, json.dumps(payload, ensure_ascii=True))
        except RedisError as exc:
            raise QueueClientError(
                f"Failed to publish to Redis queue '{queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc

    async def _pop(self, queue_name: str, *, timeout_seconds: int) -> str | None:
        try:
            result = await self._redis.blpop(queue_name, timeout=timeout_seconds)
        except RedisError as exc:
            raise QueueClientError(
                f"Failed to consume from Redis queue '{queue_name}'.",
                reason=exc.__class__.__name__,
            ) from exc
        if result is None:
            return None
        _, payload = result
        return payload

    def _require_extractor_queue_name(self) -> str:
        if self.extractor_queue_name is None:
            raise QueueClientError(
                "Extractor queue name is not configured.",
                reason="ExtractorQueueNameMissing",
            )
        return self.extractor_queue_name

    async def dispose(self) -> None:
        await self._redis.aclose()
```

```python
# tests/conftest.py
from apps.core_service.app.schemas.queue import ExtractorTaskMessage, ParserTaskMessage


class FakeQueueClient(QueueClient):
    def __init__(
        self,
        *,
        queue_name: str = "parser_queue",
        extractor_queue_name: str = "extractor_queue",
    ) -> None:
        self.queue_name = queue_name
        self.extractor_queue_name = extractor_queue_name
        self.messages: list[ParserTaskMessage] = []
        self.extractor_messages: list[ExtractorTaskMessage] = []
        self.invalid_payloads: list[str] = []
        self.publish_failures_remaining = 0
        self.consume_failures_remaining = 0

    async def publish_parser_task(self, message: ParserTaskMessage) -> None:
        if self.publish_failures_remaining > 0:
            self.publish_failures_remaining -= 1
            raise QueueClientError(
                f"Failed to publish queue message to '{self.queue_name}'.",
                reason="FakePublishFailure",
            )
        self.messages.append(message)

    async def consume_parser_task(self, *, timeout_seconds: int) -> ParserTaskMessage | None:
        del timeout_seconds
        if self.consume_failures_remaining > 0:
            self.consume_failures_remaining -= 1
            raise QueueClientError(
                f"Failed to consume queue message from '{self.queue_name}'.",
                reason="FakeConsumeFailure",
            )
        if not self.messages:
            return None
        return self.messages.pop(0)

    async def publish_extractor_task(self, message: ExtractorTaskMessage) -> None:
        if self.publish_failures_remaining > 0:
            self.publish_failures_remaining -= 1
            raise QueueClientError(
                f"Failed to publish queue message to '{self.extractor_queue_name}'.",
                reason="FakePublishFailure",
            )
        self.extractor_messages.append(message)

    async def consume_extractor_task(self, *, timeout_seconds: int) -> ExtractorTaskMessage | None:
        del timeout_seconds
        if self.consume_failures_remaining > 0:
            self.consume_failures_remaining -= 1
            raise QueueClientError(
                f"Failed to consume queue message from '{self.extractor_queue_name}'.",
                reason="FakeConsumeFailure",
            )
        if not self.extractor_messages:
            return None
        return self.extractor_messages.pop(0)
```

```python
# apps/parser_service/app/services/parser_worker.py
from apps.core_service.app.errors import QueueClientError, QueuePayloadError, StorageClientError
from apps.core_service.app.schemas.queue import ExtractorTaskMessage, ParserTaskMessage

...
        extractor_message = ExtractorTaskMessage(
            task_id=str(task.id),
            doc_type=message.doc_type,
            bucket=message.bucket,
            content_list_object_key=artifact_key,
        )
        try:
            await self._queue_client.publish_extractor_task(extractor_message)
        except QueueClientError as exc:
            await self._mark_failed(
                task.id,
                remark="Failed to publish extractor task message.",
                trace_id=trace_id,
                code="QUEUE_UNAVAILABLE",
                reason=exc.reason,
            )
            return True

        await self._mark_parsed(task.id, trace_id=trace_id, artifact_key=artifact_key)
        return True
```

```python
# apps/core_service/app/settings.py
class Settings(BaseSettings):
    ...
    parser_queue_name: str = "parser_queue"
    extractor_queue_name: str = "extractor_queue"
```

```python
# apps/parser_service/app/settings.py
class Settings(BaseSettings):
    ...
    parser_queue_name: str = "parser_queue"
    extractor_queue_name: str = "extractor_queue"
```

```python
# apps/parser_service/app/main.py
    queue_client = RedisQueueClient(
        redis_url=app_settings.redis_url,
        queue_name=app_settings.parser_queue_name,
        extractor_queue_name=app_settings.extractor_queue_name,
    )
```

- [ ] **Step 4: Run the parser worker tests to verify they pass**

Run: `.venv/bin/pytest tests/parser_service/test_worker.py -q`

Expected: PASS with the new handoff assertion included.

- [ ] **Step 5: Commit the queue handoff slice**

```bash
git add apps/core_service/app/schemas/queue.py \
  apps/core_service/app/clients/queue.py \
  apps/core_service/app/settings.py \
  apps/parser_service/app/settings.py \
  apps/parser_service/app/services/parser_worker.py \
  apps/parser_service/app/main.py \
  tests/conftest.py \
  tests/parser_service/test_worker.py
git commit -m "feat(queue): 打通解析到提取的队列交接"
```

### Task 2: Add Extraction Rule And Result Persistence

**Files:**
- Create: `apps/core_service/app/db/models/table_extraction_rule.py`
- Create: `apps/core_service/app/db/models/extracted_result.py`
- Modify: `apps/core_service/app/db/models/__init__.py`
- Create: `apps/core_service/app/repositories/table_extraction_rule_repository.py`
- Create: `apps/core_service/app/repositories/extracted_result_repository.py`
- Create: `tests/core_service/test_extraction_repositories.py`
- Create: `alembic/versions/20260401_0002_add_extraction_tables.py`

- [ ] **Step 1: Write the failing persistence tests**

```python
# tests/core_service/test_extraction_repositories.py
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import delete

from apps.core_service.app.clients.database import DatabaseClient
from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.repositories.extracted_result_repository import (
    ExtractedResultRepository,
)
from apps.core_service.app.repositories.table_extraction_rule_repository import (
    TableExtractionRuleRepository,
)


@pytest.fixture
async def async_session() -> AsyncIterator:
    client = DatabaseClient(
        "postgresql+asyncpg://postgres:postgres@localhost:25432/financial_table_extractor"
    )
    async with client.session_factory() as session:
        await session.execute(delete(ExtractedResult))
        await session.execute(delete(TableExtractionRule))
        await session.commit()
        yield session
        await session.execute(delete(ExtractedResult))
        await session.execute(delete(TableExtractionRule))
        await session.commit()
    await client.dispose()


async def test_rule_listing_and_placeholder_upsert(async_session) -> None:
    active_rule = TableExtractionRule(
        id=2001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule={"logic_match": {"required_headers": ["分部", "收入"]}},
        semantic_anchor_text="主营业务收入 管理层讨论与分析 主营业务分析",
        min_match_score=Decimal("0.900"),
        is_active="1",
    )
    inactive_rule = TableExtractionRule(
        id=2002,
        doc_type="ANNUAL_REPORT",
        target_table_code="deprecated_rule",
        target_table_name="废弃规则",
        path_fingerprints=["旧章节"],
        anchor_rule={},
        semantic_anchor_text=None,
        min_match_score=None,
        is_active="0",
    )
    async_session.add_all([active_rule, inactive_rule])
    await async_session.commit()

    rule_repo = TableExtractionRuleRepository()
    result_repo = ExtractedResultRepository()

    active_rules = await rule_repo.list_active_by_doc_type(async_session, doc_type="ANNUAL_REPORT")
    assert [rule.target_table_code for rule in active_rules] == ["main_business_revenue"]

    result = await result_repo.upsert_placeholder_not_find(
        async_session,
        result_id=9001,
        task_id=1001,
        rule=active_rule,
        remark="Extraction backbone placeholder result.",
    )
    await async_session.commit()

    assert result.id == 9001
    assert result.task_id == 1001
    assert result.rule_id == 2001
    assert result.target_table_code == "main_business_revenue"
    assert result.data_status == "NOT_FIND"
    assert result.table_data is None
    assert result.extraction_route is None
    assert result.confidence_score == Decimal("100.00")
    assert result.needs_review == "0"
```

- [ ] **Step 2: Run the persistence test to verify it fails**

Run: `.venv/bin/pytest tests/core_service/test_extraction_repositories.py -q`

Expected: FAIL with `ModuleNotFoundError` for the new models or repositories.

- [ ] **Step 3: Implement the minimal extraction storage contract**

```python
# apps/core_service/app/db/models/table_extraction_rule.py
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.core_service.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class TableExtractionRule(Base):
    __tablename__ = "t_table_extraction_rule"
    __table_args__ = (
        Index("idx_t_rule_doc_type_code", "doc_type", "target_table_code", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_table_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    path_fingerprints: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    anchor_rule: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    semantic_anchor_text: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    min_match_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    is_active: Mapped[str] = mapped_column(String(1), nullable=False, default="1")
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
```

```python
# apps/core_service/app/db/models/extracted_result.py
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.core_service.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExtractedResult(Base):
    __tablename__ = "t_extracted_result"
    __table_args__ = (
        Index("idx_t_result_task", "task_id"),
        Index("idx_t_result_review", "needs_review"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("t_table_extraction_rule.id"),
        nullable=False,
    )
    target_table_code: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    extraction_route: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_status: Mapped[str] = mapped_column(String(32), nullable=False)
    table_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    fix_table_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    start_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict[str, object] | list[object] | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    needs_review: Mapped[str] = mapped_column(String(1), nullable=False, default="0")
    remark: Mapped[str | None] = mapped_column(String(512), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
```

```python
# apps/core_service/app/repositories/table_extraction_rule_repository.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule


class TableExtractionRuleRepository:
    async def list_active_by_doc_type(
        self,
        session: AsyncSession,
        *,
        doc_type: str,
    ) -> list[TableExtractionRule]:
        statement = (
            select(TableExtractionRule)
            .where(
                TableExtractionRule.doc_type == doc_type,
                TableExtractionRule.is_active == "1",
            )
            .order_by(TableExtractionRule.id.asc())
        )
        result = await session.execute(statement)
        return list(result.scalars().all())
```

```python
# apps/core_service/app/repositories/extracted_result_repository.py
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule


class ExtractedResultRepository:
    async def upsert_placeholder_not_find(
        self,
        session: AsyncSession,
        *,
        result_id: int,
        task_id: int,
        rule: TableExtractionRule,
        remark: str,
    ) -> ExtractedResult:
        statement = select(ExtractedResult).where(
            ExtractedResult.task_id == task_id,
            ExtractedResult.rule_id == rule.id,
        )
        existing = (await session.execute(statement)).scalar_one_or_none()
        if existing is None:
            existing = ExtractedResult(
                id=result_id,
                task_id=task_id,
                rule_id=rule.id,
                target_table_code=rule.target_table_code,
                data_status="NOT_FIND",
                confidence_score=Decimal("100.00"),
                needs_review="0",
            )
            session.add(existing)

        existing.unit = None
        existing.currency = None
        existing.extraction_route = None
        existing.table_data = None
        existing.fix_table_data = None
        existing.start_page = None
        existing.end_page = None
        existing.bbox = None
        existing.remark = remark
        existing.data_status = "NOT_FIND"
        existing.confidence_score = Decimal("100.00")
        existing.needs_review = "0"
        existing.update_time = datetime.now(UTC)
        await session.flush()
        await session.refresh(existing)
        return existing
```

```python
# apps/core_service/app/db/models/__init__.py
from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.db.models.task import Task

__all__ = ["Task", "TableExtractionRule", "ExtractedResult"]
```

```python
# alembic/versions/20260401_0002_add_extraction_tables.py
"""add extraction tables"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260401_0002"
down_revision: str | None = "20260323_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "t_table_extraction_rule",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("target_table_code", sa.String(length=64), nullable=False),
        sa.Column("target_table_name", sa.String(length=128), nullable=False),
        sa.Column("path_fingerprints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("anchor_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("semantic_anchor_text", sa.String(length=2000), nullable=True),
        sa.Column("min_match_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("is_active", sa.String(length=1), nullable=False, server_default=sa.text("'1'")),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_t_rule_doc_type_code",
        "t_table_extraction_rule",
        ["doc_type", "target_table_code"],
        unique=True,
    )

    op.create_table(
        "t_extracted_result",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("target_table_code", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("extraction_route", sa.String(length=32), nullable=True),
        sa.Column("data_status", sa.String(length=32), nullable=False),
        sa.Column("table_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fix_table_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("start_page", sa.Integer(), nullable=True),
        sa.Column("end_page", sa.Integer(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("needs_review", sa.String(length=1), nullable=False, server_default=sa.text("'0'")),
        sa.Column("remark", sa.String(length=512), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["rule_id"], ["t_table_extraction_rule.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_t_result_task", "t_extracted_result", ["task_id"], unique=False)
    op.create_index("idx_t_result_review", "t_extracted_result", ["needs_review"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_t_result_review", table_name="t_extracted_result")
    op.drop_index("idx_t_result_task", table_name="t_extracted_result")
    op.drop_table("t_extracted_result")
    op.drop_index("idx_t_rule_doc_type_code", table_name="t_table_extraction_rule")
    op.drop_table("t_table_extraction_rule")
```

- [ ] **Step 4: Apply the migration**

Run: `.venv/bin/alembic upgrade head`

Expected: SUCCESS and Alembic logs show upgrade from `20260323_0001` to `20260401_0002`.

- [ ] **Step 5: Run the persistence test to verify it passes**

Run: `.venv/bin/pytest tests/core_service/test_extraction_repositories.py -q`

Expected: PASS

- [ ] **Step 6: Commit the persistence slice**

```bash
git add apps/core_service/app/db/models/__init__.py \
  apps/core_service/app/db/models/table_extraction_rule.py \
  apps/core_service/app/db/models/extracted_result.py \
  apps/core_service/app/repositories/table_extraction_rule_repository.py \
  apps/core_service/app/repositories/extracted_result_repository.py \
  tests/core_service/test_extraction_repositories.py \
  alembic/versions/20260401_0002_add_extraction_tables.py
git commit -m "feat(storage): 增加提取规则与结果持久化契约"
```

### Task 3: Implement The Extractor Worker Skeleton

**Files:**
- Create: `apps/core_service/app/services/extractor_worker.py`
- Create: `apps/core_service/app/extractor_main.py`
- Modify: `pyproject.toml`
- Modify: `tests/conftest.py`
- Create: `tests/core_service/test_extractor_worker.py`

- [ ] **Step 1: Write the failing extractor worker test**

```python
# tests/core_service/test_extractor_worker.py
from decimal import Decimal

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.services.extractor_worker import ExtractorWorker
from apps.parser_service.app.services.parser_engine import SkeletonParserEngine
from apps.parser_service.app.services.parser_worker import ParserWorker
from apps.shared.utils.snowflake import SnowflakeIdGenerator


def build_parser_worker(test_app) -> ParserWorker:
    return ParserWorker(
        session_factory=test_app.state.database_client.session_factory,
        object_storage_client=test_app.state.object_storage_client,
        queue_client=test_app.state.queue_client,
        parser_engine=SkeletonParserEngine(),
        logger=test_app.state.logger,
        repository=test_app.state.task_repository,
    )


def build_extractor_worker(test_app) -> ExtractorWorker:
    return ExtractorWorker(
        session_factory=test_app.state.database_client.session_factory,
        object_storage_client=test_app.state.object_storage_client,
        queue_client=test_app.state.queue_client,
        logger=test_app.state.logger,
        task_repository=test_app.state.task_repository,
        rule_repository=test_app.state.rule_repository,
        result_repository=test_app.state.result_repository,
        id_generator=SnowflakeIdGenerator(worker_id=9, epoch_ms=1735689600000),
    )


async def test_extractor_worker_persists_placeholder_results(async_client, test_app) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("extract.pdf", b"%PDF-1.7\nextract", "application/pdf")},
    )
    payload = response.json()

    parser_worker = build_parser_worker(test_app)
    assert await parser_worker.process_next_message(timeout_seconds=0) is True

    test_app.state.rule_repository.rules = [
        TableExtractionRule(
            id=3001,
            doc_type="ANNUAL_REPORT",
            target_table_code="main_business_revenue",
            target_table_name="主营业务收入",
            path_fingerprints=["管理层讨论与分析", "主营业务分析"],
            anchor_rule={"logic_match": {"required_headers": ["分部", "收入"]}},
            semantic_anchor_text="主营业务收入 管理层讨论与分析 主营业务分析",
            min_match_score=Decimal("0.900"),
            is_active="1",
        )
    ]

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == "COMPLETED"

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].task_id == int(payload["task_id"])
    assert rows[0].rule_id == 3001
    assert rows[0].target_table_code == "main_business_revenue"
    assert rows[0].data_status == "NOT_FIND"
    assert rows[0].confidence_score == Decimal("100.00")
```

- [ ] **Step 2: Run the extractor worker test to verify it fails**

Run: `.venv/bin/pytest tests/core_service/test_extractor_worker.py -q`

Expected: FAIL with `ModuleNotFoundError` for `ExtractorWorker`, or missing fake repositories on `test_app.state`.

- [ ] **Step 3: Implement the extractor worker, fake repositories, and CLI entrypoint**

```python
# tests/conftest.py
from datetime import UTC, datetime
from decimal import Decimal

from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule


class FakeTableExtractionRuleRepository:
    def __init__(self) -> None:
        self.rules: list[TableExtractionRule] = []

    async def list_active_by_doc_type(self, session, *, doc_type: str) -> list[TableExtractionRule]:
        del session
        normalized_doc_type = _enum_value(doc_type)
        return [
            rule
            for rule in self.rules
            if _enum_value(rule.doc_type) == normalized_doc_type and rule.is_active == "1"
        ]


class FakeExtractedResultRepository:
    def __init__(self) -> None:
        self.rows: list[ExtractedResult] = []

    async def upsert_placeholder_not_find(
        self,
        session,
        *,
        result_id: int,
        task_id: int,
        rule: TableExtractionRule,
        remark: str,
    ) -> ExtractedResult:
        del session
        for row in self.rows:
            if row.task_id == task_id and row.rule_id == rule.id:
                row.remark = remark
                row.update_time = _utc_now()
                return row

        row = ExtractedResult(
            id=result_id,
            task_id=task_id,
            rule_id=rule.id,
            target_table_code=rule.target_table_code,
            unit=None,
            currency=None,
            extraction_route=None,
            data_status="NOT_FIND",
            table_data=None,
            fix_table_data=None,
            start_page=None,
            end_page=None,
            bbox=None,
            confidence_score=Decimal("100.00"),
            needs_review="0",
            remark=remark,
            create_time=datetime.now(UTC),
            update_time=datetime.now(UTC),
        )
        self.rows.append(row)
        return row


@pytest.fixture
async def test_app() -> AsyncIterator:
    ...
    rule_repository = FakeTableExtractionRuleRepository()
    result_repository = FakeExtractedResultRepository()
    settings = Settings(
        database_url="sqlite+aiosqlite:///unused.db",
        task_id_node_id=7,
        minio_bucket=object_storage_client.bucket_name,
        parser_queue_name=queue_client.queue_name,
        extractor_queue_name=queue_client.extractor_queue_name,
    )
    app = create_app(
        settings,
        database_client=database_client,
        object_storage_client=object_storage_client,
        queue_client=queue_client,
    )
    app.state.task_repository = task_repository
    app.state.rule_repository = rule_repository
    app.state.result_repository = result_repository
    ...
```

```python
# apps/core_service/app/services/extractor_worker.py
import json
import logging
from collections.abc import Callable
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.core_service.app.clients.object_storage import ObjectStorageClient
from apps.core_service.app.clients.queue import QueueClient
from apps.core_service.app.errors import QueueClientError, QueuePayloadError, StorageClientError
from apps.core_service.app.repositories.extracted_result_repository import (
    ExtractedResultRepository,
)
from apps.core_service.app.repositories.table_extraction_rule_repository import (
    TableExtractionRuleRepository,
)
from apps.core_service.app.repositories.task_repository import TaskRepository
from apps.shared.enums.task_status import TaskStatus
from apps.shared.utils.snowflake import SnowflakeIdGenerator


class ExtractorWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        object_storage_client: ObjectStorageClient,
        queue_client: QueueClient,
        logger: logging.Logger,
        task_repository: TaskRepository,
        rule_repository: TableExtractionRuleRepository,
        result_repository: ExtractedResultRepository,
        id_generator: SnowflakeIdGenerator,
        trace_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._object_storage_client = object_storage_client
        self._queue_client = queue_client
        self._logger = logger
        self._task_repository = task_repository
        self._rule_repository = rule_repository
        self._result_repository = result_repository
        self._id_generator = id_generator
        self._trace_id_factory = trace_id_factory or (lambda: uuid4().hex)

    async def process_next_message(self, *, timeout_seconds: int) -> bool:
        try:
            message = await self._queue_client.consume_extractor_task(
                timeout_seconds=timeout_seconds
            )
        except QueuePayloadError as exc:
            self._logger.error(
                "Discarded invalid extractor queue payload.",
                extra={
                    "service": "core_service",
                    "phase": "extract_queue_consume",
                    "event": "extract_failed",
                    "task_id": None,
                    "trace_id": self._trace_id_factory(),
                    "queue_name": self._queue_client.extractor_queue_name,
                    "code": "QUEUE_PAYLOAD_INVALID",
                    "reason": exc.reason,
                },
            )
            return True
        except QueueClientError:
            raise

        if message is None:
            return False

        trace_id = self._trace_id_factory()
        try:
            artifact_bytes = await self._object_storage_client.download_bytes(
                bucket=message.bucket,
                object_key=message.content_list_object_key,
            )
            json.loads(artifact_bytes.decode("utf-8"))
        except StorageClientError as exc:
            await self._mark_failed(
                int(message.task_id),
                remark="Failed to load parser artifact from object storage.",
                trace_id=trace_id,
                code="OBJECT_STORAGE_UNAVAILABLE",
                reason=exc.reason,
            )
            return True
        except json.JSONDecodeError as exc:
            await self._mark_failed(
                int(message.task_id),
                remark="Parser artifact is not valid JSON.",
                trace_id=trace_id,
                code="ARTIFACT_INVALID",
                reason=exc.__class__.__name__,
            )
            return True

        async with self._session_factory() as session:
            try:
                task = await self._task_repository.get_by_id(session, int(message.task_id))
                if task is None:
                    return True

                rules = await self._rule_repository.list_active_by_doc_type(
                    session,
                    doc_type=message.doc_type,
                )
                for rule in rules:
                    await self._result_repository.upsert_placeholder_not_find(
                        session,
                        result_id=self._id_generator.next_id(),
                        task_id=task.id,
                        rule=rule,
                        remark="Extraction backbone placeholder result.",
                    )

                await self._task_repository.set_status(
                    session,
                    task,
                    status=TaskStatus.COMPLETED,
                    remark=None if rules else "No active extraction rules configured.",
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                self._logger.error(
                    "Failed to persist extractor result state.",
                    extra={
                        "service": "core_service",
                        "phase": "extract_complete",
                        "event": "extract_failed",
                        "task_id": message.task_id,
                        "trace_id": trace_id,
                        "code": "DATABASE_UNAVAILABLE",
                        "reason": exc.__class__.__name__,
                    },
                )
                return True

        self._logger.info(
            "Extractor task completed.",
            extra={
                "service": "core_service",
                "phase": "extract_complete",
                "event": "extract_completed",
                "task_id": message.task_id,
                "trace_id": trace_id,
                "queue_name": self._queue_client.extractor_queue_name,
                "object_key": message.content_list_object_key,
            },
        )
        return True

    async def _mark_failed(
        self,
        task_id: int,
        *,
        remark: str,
        trace_id: str,
        code: str,
        reason: str,
    ) -> None:
        async with self._session_factory() as session:
            try:
                task = await self._task_repository.get_by_id(session, task_id)
                if task is not None:
                    await self._task_repository.set_status(
                        session,
                        task,
                        status=TaskStatus.FAILED,
                        remark=remark,
                    )
                    await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                return

        self._logger.error(
            "Extractor task failed.",
            extra={
                "service": "core_service",
                "phase": "extract_failed",
                "event": "extract_failed",
                "task_id": task_id,
                "trace_id": trace_id,
                "code": code,
                "reason": reason,
            },
        )
```

```python
# apps/core_service/app/extractor_main.py
import asyncio
import logging

from apps.core_service.app.clients.database import DatabaseClient
from apps.core_service.app.clients.object_storage import MinioObjectStorageClient
from apps.core_service.app.clients.queue import RedisQueueClient
from apps.core_service.app.logging_config import configure_logging
from apps.core_service.app.repositories.extracted_result_repository import (
    ExtractedResultRepository,
)
from apps.core_service.app.repositories.table_extraction_rule_repository import (
    TableExtractionRuleRepository,
)
from apps.core_service.app.repositories.task_repository import TaskRepository
from apps.core_service.app.services.extractor_worker import ExtractorWorker
from apps.core_service.app.settings import Settings, get_settings
from apps.shared.utils.snowflake import SnowflakeIdGenerator


async def run(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    logger = logging.getLogger(f"{app_settings.app_name}-extractor")

    database_client = DatabaseClient(app_settings.database_url)
    object_storage_client = MinioObjectStorageClient(
        endpoint=app_settings.minio_endpoint,
        access_key=app_settings.minio_root_user,
        secret_key=app_settings.minio_root_password,
        bucket_name=app_settings.minio_bucket,
    )
    queue_client = RedisQueueClient(
        redis_url=app_settings.redis_url,
        queue_name=app_settings.parser_queue_name,
        extractor_queue_name=app_settings.extractor_queue_name,
    )
    worker = ExtractorWorker(
        session_factory=database_client.session_factory,
        object_storage_client=object_storage_client,
        queue_client=queue_client,
        logger=logger,
        task_repository=TaskRepository(),
        rule_repository=TableExtractionRuleRepository(),
        result_repository=ExtractedResultRepository(),
        id_generator=SnowflakeIdGenerator(
            worker_id=app_settings.task_id_node_id,
            epoch_ms=app_settings.task_id_epoch_ms,
        ),
    )

    await database_client.healthcheck()
    await object_storage_client.healthcheck()
    await queue_client.healthcheck()

    try:
        while True:
            await worker.process_next_message(timeout_seconds=5)
    finally:
        await queue_client.dispose()
        await object_storage_client.dispose()
        await database_client.dispose()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return None
```

```toml
# pyproject.toml
[project.scripts]
financial-table-extractor = "apps.core_service.app.main:main"
financial-table-parser = "apps.parser_service.app.main:main"
financial-table-extractor-worker = "apps.core_service.app.extractor_main:main"
```

- [ ] **Step 4: Run the targeted worker tests**

Run: `.venv/bin/pytest tests/parser_service/test_worker.py tests/core_service/test_extractor_worker.py -q`

Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/pytest -q`

Expected: PASS with the suite count increasing from `10` to `13`.

- [ ] **Step 6: Commit the extractor worker slice**

```bash
git add apps/core_service/app/services/extractor_worker.py \
  apps/core_service/app/extractor_main.py \
  pyproject.toml \
  tests/conftest.py \
  tests/core_service/test_extractor_worker.py
git commit -m "feat(extractor): 补齐提取骨架执行器"
```

## Follow-Up Plans After This Plan Lands

`Extraction Backbone` 合并后，继续按下面顺序推进，避免把多个高风险子系统绑在一个分支里：

1. `Pagination Merge And Logical Table Builder`
   输入为真实 MinerU `content_list.json`，输出 `LogicalTable` 列表；在这一阶段引入跨页续表识别与重复表头剔除。
2. `Semantic Routing, Fast Track, And LLM Fallback`
   新增目录树构建、路径指纹粗排、锚点规则精排、路由决策；这时再引入 `t_document_toc` 与 `semantic_vector`。
3. `Normalization And Confidence Scoring`
   把单位/币种、`0.00/null/NOT_DISCLOSED/NOT_FIND` 语义、`confidence_score`、`PENDING_REVIEW` 判定补齐。
4. `Traceability Delivery, Review Queue, And Retrigger API`
   增加 bbox 映射 API、前端复核联动、局部重跑入口和结果回写。

## Self-Review

Spec coverage 检查：

- 本计划覆盖了当前最关键的断点：把 `PARSED` 后的空白链路补成“有队列、有规则、有结果、有终态”的最小闭环。
- `Phase 2` 逻辑表构建、`Phase 3` 语义路由、`Phase 4` 归一化、`Phase 5` 置信度、`Phase 6` 溯源 UI 没有遗漏，而是明确拆到后续计划，避免单计划过载。

Placeholder 扫描：

- 本文没有使用 `TODO` / `TBD` / “类似 Task N” 这类不可执行描述。
- 每个代码变更步骤都包含了具体文件和具体代码片段。

Type consistency 检查：

- 队列消息名统一为 `ExtractorTaskMessage`。
- worker 统一消费 `content_list_object_key`。
- 占位结果统一写入 `data_status="NOT_FIND"`、`confidence_score=100.00`、`needs_review="0"`。
