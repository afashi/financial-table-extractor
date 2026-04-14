# Persistent TOC And Vector Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在真实 parser artifact 基线上补齐 `t_document_toc` 持久化、`semantic_vector` 存储和 BGE-M3 向量打分，把当前纯规则路由升级为“TOC 粗排 + 向量增强精排”。

**Architecture:** Extractor Worker 继续把 `content_list.json` 读入内存，但在进入路由前先从 heading block / `metadata.section_path` 构建 TOC 树并持久化到 PostgreSQL。规则表新增 `semantic_vector`，由独立同步命令用 `BAAI/bge-m3` 生成 1024 维 dense embedding；`TableRouter` 改为异步混合路由器，先用 TOC 判断章节是否存在，再对候选逻辑表综合 `path_fingerprints + anchor_rule + vector similarity` 打分。

**Tech Stack:** Python 3.13, SQLAlchemy 2.x, Alembic, PostgreSQL + pgvector, FlagEmbedding (`BGEM3FlagModel`), pytest

---

## File Structure

- Modify: `pyproject.toml`
- Create: `alembic/versions/20260413_0003_add_document_toc_and_rule_vectors.py`
- Create: `apps/core_service/app/db/models/document_toc.py`
- Modify: `apps/core_service/app/db/models/table_extraction_rule.py`
- Create: `apps/core_service/app/repositories/document_toc_repository.py`
- Modify: `apps/core_service/app/repositories/table_extraction_rule_repository.py`
- Create: `apps/core_service/app/schemas/toc.py`
- Create: `apps/core_service/app/clients/embedding.py`
- Create: `apps/core_service/app/services/document_toc_builder.py`
- Modify: `apps/core_service/app/services/table_router.py`
- Modify: `apps/core_service/app/services/extractor_worker.py`
- Modify: `apps/core_service/app/settings.py`
- Modify: `apps/core_service/app/extractor_main.py`
- Create: `apps/core_service/app/vector_sync.py`
- Create: `tests/core_service/test_document_toc_builder.py`
- Create: `tests/core_service/test_embedding_client.py`
- Modify: `tests/core_service/test_table_router.py`
- Modify: `tests/core_service/test_extractor_worker.py`
- Modify: `tests/conftest.py`

## Preflight

- [ ] **Step 1: Verify the current routing baseline**

Run: `.venv/bin/python -m pytest tests/core_service/test_table_router.py tests/core_service/test_extractor_worker.py -q`
Expected: PASS

- [ ] **Step 2: Verify the current database baseline**

Run: `.venv/bin/alembic upgrade head`
Expected: PASS with the current two revisions applied

### Task 1: Add TOC Draft Models And Builder Logic

**Files:**
- Create: `apps/core_service/app/schemas/toc.py`
- Create: `apps/core_service/app/services/document_toc_builder.py`
- Create: `tests/core_service/test_document_toc_builder.py`

- [ ] **Step 1: Write the failing TOC builder test**

```python
from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.services.document_toc_builder import DocumentTocBuilder


def _text_block(*, page_idx: int, y0: float, text: str, section_path: list[str], block_role: str = "heading") -> ArtifactContentBlock:
    return ArtifactContentBlock(
        type="text",
        page_idx=page_idx,
        bbox=[0.0, y0, 200.0, y0 + 20.0],
        text=text,
        metadata={
            "section_path": section_path,
            "block_role": block_role,
        },
    )


def test_document_toc_builder_creates_tree_and_page_ranges() -> None:
    blocks = [
        _text_block(page_idx=0, y0=0.0, text="管理层讨论与分析", section_path=["管理层讨论与分析"]),
        _text_block(
            page_idx=0,
            y0=24.0,
            text="主营业务分析",
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
        ArtifactContentBlock(
            type="table",
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 180.0],
            metadata={"section_path": ["管理层讨论与分析", "主营业务分析"]},
            table_body=[["分部", "收入"], ["境内", "100"]],
        ),
    ]

    nodes = DocumentTocBuilder().build(task_id=1001, blocks=blocks)

    assert [node.title for node in nodes] == ["管理层讨论与分析", "主营业务分析"]
    assert nodes[0].level == 1
    assert nodes[0].parent_title is None
    assert nodes[0].start_page == 0
    assert nodes[0].end_page == 1
    assert nodes[1].level == 2
    assert nodes[1].parent_title == "管理层讨论与分析"
    assert nodes[1].start_page == 0
    assert nodes[1].end_page == 1
```

- [ ] **Step 2: Run the TOC builder test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core_service/test_document_toc_builder.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.services.document_toc_builder'`

- [ ] **Step 3: Implement TOC draft models and builder**

```python
from pydantic import BaseModel


class TocDraftNode(BaseModel):
    title: str
    level: int
    start_page: int
    end_page: int
    start_y: float | None = None
    end_y: float | None = None
    parent_title: str | None = None
```

```python
from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.toc import TocDraftNode


class DocumentTocBuilder:
    def build(self, *, task_id: int, blocks: list[ArtifactContentBlock]) -> list[TocDraftNode]:
        del task_id
        nodes_by_path: dict[tuple[str, ...], TocDraftNode] = {}

        for block in blocks:
            path = self._path_for_block(block)
            if not path:
                continue

            for depth in range(1, len(path) + 1):
                current_path = tuple(path[:depth])
                node = nodes_by_path.get(current_path)
                page_idx = block.page_idx
                y0 = float(block.bbox[1]) if len(block.bbox) > 1 else None
                y1 = float(block.bbox[3]) if len(block.bbox) > 3 else None

                if node is None:
                    nodes_by_path[current_path] = TocDraftNode(
                        title=current_path[-1],
                        level=depth,
                        start_page=page_idx,
                        end_page=page_idx,
                        start_y=y0,
                        end_y=y1,
                        parent_title=current_path[-2] if depth > 1 else None,
                    )
                    continue

                node.end_page = page_idx
                node.end_y = y1

        return list(nodes_by_path.values())

    def _path_for_block(self, block: ArtifactContentBlock) -> list[str]:
        raw_path = block.metadata.get("section_path")
        if isinstance(raw_path, list) and raw_path:
            return [str(item).strip() for item in raw_path if str(item).strip()]
        return []
```

- [ ] **Step 4: Run the TOC builder suite**

Run: `.venv/bin/python -m pytest tests/core_service/test_document_toc_builder.py tests/core_service/test_logical_table_builder.py -q`
Expected: PASS

- [ ] **Step 5: Commit the TOC builder**

```bash
git add apps/core_service/app/schemas/toc.py apps/core_service/app/services/document_toc_builder.py tests/core_service/test_document_toc_builder.py
git commit -m "feat(router): 新增目录树构建器"
```

### Task 2: Persist TOC And Rule Vectors In PostgreSQL

**Files:**
- Modify: `pyproject.toml`
- Create: `alembic/versions/20260413_0003_add_document_toc_and_rule_vectors.py`
- Create: `apps/core_service/app/db/models/document_toc.py`
- Modify: `apps/core_service/app/db/models/table_extraction_rule.py`
- Create: `apps/core_service/app/repositories/document_toc_repository.py`
- Modify: `apps/core_service/app/repositories/table_extraction_rule_repository.py`
- Modify: `tests/conftest.py`
- Modify: `tests/core_service/test_extractor_worker.py`

- [ ] **Step 1: Write the failing persistence test**

```python
import json

from apps.core_service.app.db.models.task import Task
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.queue import ExtractorTaskMessage
from apps.core_service.app.services.extractor_worker import ExtractorWorker


async def test_extractor_worker_persists_document_toc_before_routing(test_app) -> None:
    task = Task(
        id=1001,
        doc_type="ANNUAL_REPORT",
        file_name="annual.pdf",
        file_hash="hash-1",
        file_size=128,
        status="PARSED",
        remark=None,
    )
    await test_app.state.task_repository.create(None, task)
    await test_app.state.object_storage_client.upload_bytes(
        object_key="tasks/1001/content_list.json",
        data=json.dumps(
            [
                {
                    "type": "text",
                    "page_idx": 0,
                    "bbox": [0.0, 0.0, 200.0, 20.0],
                    "text": "管理层讨论与分析",
                    "metadata": {
                        "section_path": ["管理层讨论与分析"],
                        "block_role": "heading",
                    },
                },
                {
                    "type": "text",
                    "page_idx": 0,
                    "bbox": [0.0, 24.0, 200.0, 44.0],
                    "text": "主营业务分析",
                    "metadata": {
                        "section_path": ["管理层讨论与分析", "主营业务分析"],
                        "block_role": "heading",
                    },
                },
            ],
            ensure_ascii=True,
        ).encode("utf-8"),
        content_type="application/json",
    )
    test_app.state.rule_repository.rules = [
        TableExtractionRule(
            id=3001,
            doc_type="ANNUAL_REPORT",
            target_table_code="main_business_revenue",
            target_table_name="主营业务分部收入",
            path_fingerprints=["管理层讨论与分析", "主营业务分析"],
            anchor_rule=None,
            semantic_anchor_text=None,
            min_match_score=None,
            is_active="1",
        )
    ]

    worker = ExtractorWorker(
        session_factory=test_app.state.database_client.session_factory,
        object_storage_client=test_app.state.object_storage_client,
        queue_client=test_app.state.queue_client,
        logger=test_app.state.logger,
        task_repository=test_app.state.task_repository,
        rule_repository=test_app.state.rule_repository,
        result_repository=test_app.state.result_repository,
        document_toc_repository=test_app.state.document_toc_repository,
        id_generator=test_app.state.task_id_generator,
    )

    assert await worker.process_message(
        ExtractorTaskMessage(
            task_id="1001",
            doc_type="ANNUAL_REPORT",
            bucket=test_app.state.object_storage_client.bucket_name,
            content_list_object_key="tasks/1001/content_list.json",
        )
    ) is True

    toc_rows = test_app.state.document_toc_repository.rows_by_task[1001]
    assert [row.title for row in toc_rows] == ["管理层讨论与分析", "主营业务分析"]
    assert toc_rows[1].parent_id == toc_rows[0].id
```

- [ ] **Step 2: Run the persistence test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core_service/test_extractor_worker.py::test_extractor_worker_persists_document_toc_before_routing -q`
Expected: FAIL because `document_toc_repository` and the new worker wiring do not exist

- [ ] **Step 3: Add pgvector dependency, migration, models, and repositories**

```toml
[project]
dependencies = [
    "alembic>=1.16.5,<2",
    "asyncpg>=0.30.0,<1",
    "fastapi>=0.116.1,<1",
    "minio>=7.2.18,<8",
    "pgvector>=0.3.6,<1",
    "pydantic-settings>=2.11.0,<3",
    "python-multipart>=0.0.20,<1",
    "redis>=6.4.0,<7",
    "sqlalchemy>=2.0.43,<3",
    "uvicorn>=0.35.0,<1",
]
```

```python
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.core_service.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class DocumentToc(Base):
    __tablename__ = "t_document_toc"
    __table_args__ = (Index("idx_t_document_toc_task", "task_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    start_y: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    end_y: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("t_document_toc.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    update_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
```

```python
from pgvector.sqlalchemy import Vector

semantic_vector: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
```

```python
"""add document toc and rule vectors"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "t_document_toc",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("start_y", sa.Numeric(10, 4), nullable=True),
        sa.Column("end_y", sa.Numeric(10, 4), nullable=True),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["parent_id"], ["t_document_toc.id"]),
    )
    op.create_index("idx_t_document_toc_task", "t_document_toc", ["task_id"], unique=False)
    op.add_column("t_table_extraction_rule", sa.Column("semantic_vector", Vector(1024), nullable=True))
    op.create_index(
        "idx_t_rule_vector",
        "t_table_extraction_rule",
        ["semantic_vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"semantic_vector": "vector_cosine_ops"},
    )
```

- [ ] **Step 4: Apply the migration and run the persistence suite**

Run: `.venv/bin/alembic upgrade head && .venv/bin/python -m pytest tests/core_service/test_document_toc_builder.py -q`
Expected: PASS

- [ ] **Step 5: Commit the persistence layer**

```bash
git add pyproject.toml alembic/versions/20260413_0003_add_document_toc_and_rule_vectors.py apps/core_service/app/db/models/document_toc.py apps/core_service/app/db/models/table_extraction_rule.py apps/core_service/app/repositories/document_toc_repository.py tests/conftest.py
git commit -m "feat(router): 落地目录树与规则向量存储"
```

### Task 3: Add BGE-M3 Embedding Client And Rule Vector Sync Command

**Files:**
- Create: `apps/core_service/app/clients/embedding.py`
- Create: `apps/core_service/app/vector_sync.py`
- Modify: `apps/core_service/app/settings.py`
- Modify: `apps/core_service/app/repositories/table_extraction_rule_repository.py`
- Create: `tests/core_service/test_embedding_client.py`

- [ ] **Step 1: Write the failing embedding and sync tests**

```python
from apps.core_service.app.clients.embedding import BGEM3EmbeddingClient


class FakeModel:
    def encode(self, texts, batch_size, max_length):
        del batch_size, max_length
        return {"dense_vecs": [[1.0, 0.0], [0.0, 1.0]]}


async def test_bge_m3_client_returns_dense_vectors() -> None:
    client = BGEM3EmbeddingClient(model=FakeModel())

    vectors = await client.encode(["主营业务分析", "其他章节"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
```

```python
from dataclasses import dataclass

from apps.core_service.app.vector_sync import sync_rule_vectors


@dataclass
class FakeRule:
    id: int
    semantic_anchor_text: str | None
    target_table_name: str
    semantic_vector: list[float] | None = None


class FakeRuleRepository:
    def __init__(self) -> None:
        self.rules = [FakeRule(id=1, semantic_anchor_text="主营业务分部收入表", target_table_name="主营业务分部收入")]

    async def list_rules_missing_vectors(self, session):
        del session
        return [rule for rule in self.rules if rule.semantic_vector is None]

    async def update_semantic_vectors(self, session, *, pairs):
        del session
        for rule, vector in pairs:
            rule.semantic_vector = vector


class FakeEmbeddingClient:
    def __init__(self, vectors) -> None:
        self._vectors = vectors

    async def encode(self, texts):
        assert texts == ["主营业务分部收入表"]
        return self._vectors


async def test_sync_rule_vectors_updates_missing_vectors() -> None:
    repository = FakeRuleRepository()

    count = await sync_rule_vectors(
        session=object(),
        rule_repository=repository,
        embedding_client=FakeEmbeddingClient([[1.0, 0.0]]),
    )

    assert count == 1
    assert repository.rules[0].semantic_vector == [1.0, 0.0]
```

- [ ] **Step 2: Run the embedding tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core_service/test_embedding_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.clients.embedding'`

- [ ] **Step 3: Implement the embedding client and vector sync command**

```python
import asyncio
from collections.abc import Sequence

from FlagEmbedding import BGEM3FlagModel


class EmbeddingClient:
    async def encode(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class BGEM3EmbeddingClient(EmbeddingClient):
    def __init__(self, *, model_name: str = "BAAI/bge-m3", use_fp16: bool = True, model=None) -> None:
        self._model = model or BGEM3FlagModel(model_name, use_fp16=use_fp16)

    async def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode_blocking, list(texts))

    def _encode_blocking(self, texts: list[str]) -> list[list[float]]:
        output = self._model.encode(texts, batch_size=8, max_length=8192)
        return [list(map(float, row)) for row in output["dense_vecs"]]
```

```python
async def sync_rule_vectors(*, session, rule_repository, embedding_client) -> int:
    rules = await rule_repository.list_rules_missing_vectors(session)
    if not rules:
        return 0

    texts = [rule.semantic_anchor_text or rule.target_table_name for rule in rules]
    vectors = await embedding_client.encode(texts)
    await rule_repository.update_semantic_vectors(session, pairs=list(zip(rules, vectors, strict=True)))
    await session.commit()
    return len(rules)
```

- [ ] **Step 4: Run the embedding/vector sync suite**

Run: `.venv/bin/python -m pytest tests/core_service/test_embedding_client.py -q`
Expected: PASS

- [ ] **Step 5: Commit vector sync support**

```bash
git add apps/core_service/app/clients/embedding.py apps/core_service/app/vector_sync.py apps/core_service/app/settings.py apps/core_service/app/repositories/table_extraction_rule_repository.py tests/core_service/test_embedding_client.py
git commit -m "feat(router): 新增规则向量同步命令"
```

### Task 4: Upgrade Router And Extractor Worker To Use TOC And Vector Scores

**Files:**
- Modify: `apps/core_service/app/services/table_router.py`
- Modify: `apps/core_service/app/services/extractor_worker.py`
- Modify: `apps/core_service/app/extractor_main.py`
- Modify: `tests/core_service/test_table_router.py`
- Modify: `tests/core_service/test_extractor_worker.py`

- [ ] **Step 1: Write the failing vector-aware router test**

```python
from decimal import Decimal

from apps.core_service.app.services.table_router import TableRouter


class FakeEmbeddingClient:
    def __init__(self, vectors):
        self.vectors = list(vectors)

    async def encode(self, texts):
        del texts
        return self.vectors


async def test_router_promotes_candidate_when_vector_score_clears_threshold() -> None:
    from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
    from apps.core_service.app.schemas.artifact import ArtifactContentBlock
    from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment
    from apps.core_service.app.schemas.toc import TocDraftNode

    rule = TableExtractionRule(
        id=3001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务分部收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule=None,
        semantic_anchor_text="主营业务分部收入表",
        semantic_vector=[1.0, 0.0],
        min_match_score=Decimal("0.850"),
        is_active="1",
    )
    logical_table = LogicalTable(
        logical_table_id="lt-1",
        start_page=2,
        end_page=2,
        header=["分部", "营业收入"],
        rows=[["境内", "100"]],
        section_path=["管理层讨论与分析", "主营业务分析"],
        segments=[LogicalTableSegment(page_idx=2, block_index=0, bbox=[0.0, 40.0, 300.0, 180.0])],
        context_before=["主营业务分部收入表"],
    )
    content_blocks = [
        ArtifactContentBlock(
            type="text",
            page_idx=2,
            bbox=[0.0, 0.0, 300.0, 24.0],
            text="主营业务分部收入表",
            metadata={"section_path": ["管理层讨论与分析", "主营业务分析"]},
        )
    ]
    toc_nodes = [
        TocDraftNode(
            title="管理层讨论与分析",
            level=1,
            start_page=0,
            end_page=3,
            start_y=0.0,
            end_y=180.0,
            parent_title=None,
        ),
        TocDraftNode(
            title="主营业务分析",
            level=2,
            start_page=2,
            end_page=3,
            start_y=0.0,
            end_y=180.0,
            parent_title="管理层讨论与分析",
        ),
    ]
    router = TableRouter(embedding_client=FakeEmbeddingClient([[0.96, 0.04]]))

    decision = await router.route(
        rule=rule,
        toc_nodes=toc_nodes,
        logical_tables=[logical_table],
        content_blocks=content_blocks,
    )

    assert decision.decision == "FAST_TRACK"
    assert decision.semantic_match_score == Decimal("0.960")
```

- [ ] **Step 2: Run the vector-aware router test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core_service/test_table_router.py::test_router_promotes_candidate_when_vector_score_clears_threshold -q`
Expected: FAIL because `TableRouter.route` is still synchronous and does not accept `toc_nodes`

- [ ] **Step 3: Implement TOC-aware hybrid routing and worker persistence**

```python
from decimal import Decimal
from math import sqrt


class TableRouter:
    def __init__(self, *, embedding_client) -> None:
        self._embedding_client = embedding_client

    async def route(self, *, rule, toc_nodes, logical_tables, content_blocks):
        if not self._toc_contains_path(rule.path_fingerprints, toc_nodes):
            return RouteDecision(
                decision="NOT_FIND",
                best_score=Decimal("0.000"),
                matched_path=[],
                matched_table=None,
                context_blocks=[],
                remark="Section fingerprint was not found in the persisted TOC tree.",
                semantic_match_score=Decimal("0.000"),
            )

        section_tables = [
            table for table in logical_tables if self._path_matches(rule.path_fingerprints, table.section_path)
        ]
        if not section_tables:
            return RouteDecision(
                decision="SLOW_TRACK",
                best_score=Decimal("0.000"),
                matched_path=list(rule.path_fingerprints),
                matched_table=None,
                context_blocks=self._text_only_context(rule=rule, content_blocks=content_blocks),
                remark="TOC matched but no standard logical table was found in the section.",
                semantic_match_score=Decimal("0.000"),
            )

        candidate_texts = [self._candidate_text(table) for table in section_tables]
        candidate_vectors = await self._embedding_client.encode(candidate_texts)
        scored_tables = []
        for table, vector in zip(section_tables, candidate_vectors, strict=True):
            deterministic_score = self._candidate_score(rule=rule, table=table)
            semantic_score = self._cosine_similarity(rule.semantic_vector, vector)
            total_score = min(deterministic_score + (semantic_score * Decimal("0.350")), Decimal("1.000"))
            scored_tables.append((table, total_score, semantic_score))

        best_table, best_score, semantic_score = max(scored_tables, key=lambda item: item[1])
        if best_score >= self._threshold(rule):
            return RouteDecision(
                decision="FAST_TRACK",
                best_score=best_score,
                matched_path=list(best_table.section_path),
                matched_table=best_table,
                context_blocks=list(best_table.context_before),
                remark="Matched logical table by TOC, anchor rules, and vector score.",
                semantic_match_score=semantic_score,
            )
        return RouteDecision(
            decision="SLOW_TRACK",
            best_score=best_score,
            matched_path=list(best_table.section_path),
            matched_table=None,
            context_blocks=self._section_context(rule=rule, content_blocks=content_blocks, logical_tables=section_tables),
            remark="Section matched but no logical table cleared the combined threshold.",
            semantic_match_score=semantic_score,
        )
```

```python
toc_drafts = self._document_toc_builder.build(task_id=task.id, blocks=content_blocks)
toc_nodes = await self._document_toc_repository.replace_for_task(session, task_id=task.id, drafts=toc_drafts)

decision = await self._table_router.route(
    rule=rule,
    toc_nodes=toc_nodes,
    logical_tables=logical_tables,
    content_blocks=content_blocks,
)
```

- [ ] **Step 4: Run the routing and extractor regressions**

Run: `.venv/bin/python -m pytest tests/core_service/test_document_toc_builder.py tests/core_service/test_table_router.py tests/core_service/test_extractor_worker.py -q`
Expected: PASS

- [ ] **Step 5: Commit the hybrid router**

```bash
git add apps/core_service/app/services/table_router.py apps/core_service/app/services/extractor_worker.py apps/core_service/app/extractor_main.py tests/core_service/test_table_router.py tests/core_service/test_extractor_worker.py
git commit -m "feat(router): 接入目录树与向量增强路由"
```

## Final Verification

- [ ] **Step 1: Rebuild schema and run focused tests**

Run: `.venv/bin/alembic upgrade head && .venv/bin/python -m pytest tests/core_service/test_document_toc_builder.py tests/core_service/test_embedding_client.py tests/core_service/test_table_router.py tests/core_service/test_extractor_worker.py -q`
Expected: PASS

- [ ] **Step 2: Run the full repository suite**

Run: `.venv/bin/python -m pytest tests -q`
Expected: PASS

## Assumptions

- P0 已经保证 canonical artifact 包含稳定的 `metadata.section_path`，并对 heading text block 标注 `metadata.block_role="heading"`。
- `semantic_vector` 使用 Hugging Face 官方 `BAAI/bge-m3` dense embedding，向量维度固定为 1024。来源：模型卡 `https://huggingface.co/BAAI/bge-m3`
- 本阶段不引入 rule 管理后台；规则向量通过独立同步命令补齐，后续如有规则 CRUD，再把 `vector_sync` 逻辑并入管理写路径。
