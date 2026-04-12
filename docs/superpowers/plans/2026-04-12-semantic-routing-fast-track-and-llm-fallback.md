# Semantic Routing, Fast Track, And LLM Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 `logical_tables.json` 基线上补齐 Phase 3 的可运行主链路：按规则完成章节粗排与锚点精排，命中标准表时走规则快车道，章节命中但标准表缺失时走可插拔 LLM 慢车道，并把结构化结果写入 `t_extracted_result`。

**Architecture:** 保持 `parser_service -> extractor_queue -> core extractor worker` 主链路不变，不新增数据库表，也不引入 `pgvector`、嵌入服务或 review queue。本阶段在 Core Service 内新增一个纯内存 `TableRouter`，基于 `path_fingerprints + anchor_rule + semantic_anchor_text` 做确定性打分；`ExtractorWorker` 继续上传 `logical_tables.json`，随后为每条规则执行 `FAST_TRACK | SLOW_TRACK | NOT_FIND` 三态决策，并通过统一的 `ExtractionOutcome` 写回结果表。

**Tech Stack:** Python 3.13, Pydantic v2, SQLAlchemy 2.x, FastAPI, httpx, MinIO, pytest

---

## Requirement And Design Comparison

已对齐的部分：

- `requirement.md` 3.2/3.3 与 `design.md` Phase 3 都要求先按 `path_fingerprints` 缩小章节，再按 `anchor_rule` 命中标准表，最后在“章节存在但标准表未命中”时启用 LLM fallback。
- 当前仓库已经具备 Phase 3 的两个关键输入：`content_list.json` 和 `logical_tables.json`。`ExtractorWorker` 能稳定加载 canonical artifact，并且 `LogicalTableBuilder` 已经完成跨页合并。
- `t_table_extraction_rule` 已经落地所需字段：`path_fingerprints`、`anchor_rule`、`semantic_anchor_text`、`min_match_score` 都在模型里。
- `t_extracted_result` 已经具备 Phase 3 需要写回的字段：`data_status`、`extraction_route`、`table_data`、`start_page`、`end_page`、`bbox`、`confidence_score`、`remark`。

当前缺口：

- `apps/core_service/app/schemas/logical_table.py` 还没有保留 `section_path`，导致 `logical_tables.json` 无法直接支持 Phase 3 的章节粗排。
- `apps/core_service/app/services/extractor_worker.py` 目前仍然对所有规则写占位 `NOT_FIND`，没有真实路由、快车道提取或慢车道兜底。
- 仓库还没有 `TableRouter`、`FastTrackExtractor`、`LLMFallbackClient` 这三个 Phase 3 核心构件。
- 当前 runtime 已有 `httpx`，但 `Settings` 和 `extractor_main.py` 尚未提供 LLM fallback 的配置与装配入口。

本计划的设计决策：

- 这一版把“语义路由”限定为**确定性可测试的路由**：`path_fingerprints`、表头逻辑匹配、上下文关键词、标题正则，以及基于 `semantic_anchor_text` 的轻量词汇重叠加分。真正的向量嵌入与 `pgvector` 保留到下一份专门的向量化计划。
- 不新建 `t_document_toc`。当前 parser skeleton 还没有稳定的标题层级 contract，本阶段直接从 `logical_tables` 的 `section_path` 和 `content_list` 的文本块构建**内存态章节上下文**即可满足路由和 fallback。
- 不引入 `pandas`。当前 `LogicalTable` 已经是行列结构化结果，快车道先直接输出 `headers + rows + bbox`，把单位归一化、异常表格清洗和 DataFrame 后处理留给下一阶段。
- LLM fallback 先做成**可插拔 HTTP client**。默认禁用；启用时要求返回严格 JSON。这样可以先把编排与测试链路落地，不把模型供应商绑定写死在本计划里。

## Scope Check

`requirement.md` 的 Phase 3 到 Phase 6 仍然是连续链路，但这一阶段不能再把“向量检索、单位归一化、置信度体系、人工复核、前端溯源”继续堆进同一份计划。本计划只覆盖：

1. `LogicalTable` 携带 `section_path`
2. 纯内存 `TableRouter` 进行章节粗排 + 锚点精排
3. 规则快车道把命中的 `LogicalTable` 直接转成 `ExtractionOutcome`
4. 可插拔 HTTP LLM fallback 在章节命中但标准表缺失时返回 `SUCCESS | NOT_DISCLOSED`
5. `ExtractorWorker` 基于三态决策写回 `t_extracted_result`

本计划明确不做：

- `pgvector`、向量嵌入生成、向量检索或向量召回表
- `t_document_toc` 或任意持久化 TOC 表
- 单位/币种归一化
- 细粒度置信度扣分公式
- `PENDING_REVIEW` 队列、traceability API、前端复核界面

## File Structure

本计划只创建或修改下面这些文件：

- Modify: `apps/core_service/app/schemas/logical_table.py`
  给 `LogicalTable` 增加 `section_path`，把 Phase 2 工件补成 Phase 3 可路由输入。
- Modify: `apps/core_service/app/services/logical_table_builder.py`
  在构建逻辑表时保留表格块的 `metadata.section_path`。
- Create: `apps/core_service/app/schemas/routing.py`
  定义 `RouteDecision`、`RoutingCandidate` 等 Phase 3 中间模型。
- Create: `apps/core_service/app/schemas/extraction.py`
  定义 `ExtractionOutcome`，统一快车道、慢车道和 `NOT_FIND` 的持久化输入。
- Create: `apps/core_service/app/services/table_router.py`
  实现章节粗排、锚点规则打分和 `FAST_TRACK | SLOW_TRACK | NOT_FIND` 决策。
- Create: `apps/core_service/app/services/fast_track_extractor.py`
  把命中的 `LogicalTable` 转为最终 `table_data/bbox/page range`。
- Modify: `apps/core_service/app/repositories/extracted_result_repository.py`
  新增 `upsert_result(...)`，统一写入真实提取结果。
- Modify: `apps/core_service/app/errors.py`
  增加 `LLMFallbackClientError`。
- Create: `apps/core_service/app/clients/llm_fallback.py`
  提供 `DisabledLLMFallbackClient` 与 `HttpLLMFallbackClient`。
- Modify: `apps/core_service/app/settings.py`
  增加 LLM fallback 配置项。
- Modify: `apps/core_service/app/extractor_main.py`
  装配默认禁用或 HTTP 版 LLM client。
- Modify: `apps/core_service/app/services/extractor_worker.py`
  接入 router、fast track、fallback 和真实结果写回。
- Modify: `tests/core_service/test_logical_table_builder.py`
  回归 `section_path` 透传。
- Create: `tests/core_service/test_table_router.py`
  覆盖 `FAST_TRACK`、`SLOW_TRACK`、`NOT_FIND` 三种路由决策。
- Create: `tests/core_service/test_fast_track_extractor.py`
  覆盖快车道结果组装。
- Modify: `tests/core_service/test_extraction_repositories.py`
  覆盖真实结果 upsert。
- Create: `tests/core_service/test_llm_fallback_client.py`
  覆盖禁用态 fallback 与 HTTP 响应解析。
- Modify: `tests/conftest.py`
  增加 `FakeLLMFallbackClient`，并让 `FakeExtractedResultRepository` 支持 `upsert_result(...)`。
- Modify: `tests/core_service/test_extractor_worker.py`
  覆盖 worker 的快车道、慢车道、`NOT_FIND` 与 fallback 失败路径。

## Preflight

- [ ] **Step 1: Verify the current Phase 2 baseline before changing routing behavior**

Run: `.venv/bin/pytest tests/core_service/test_logical_table_builder.py tests/core_service/test_extractor_worker.py -q`

Expected: PASS with `13 passed`

- [ ] **Step 2: Verify the repository baseline before starting Phase 3**

Run: `.venv/bin/pytest -q`

Expected: PASS with `27 passed`

## Task 1: Preserve Section Path In Logical Tables

**Files:**
- Modify: `apps/core_service/app/schemas/logical_table.py`
- Modify: `apps/core_service/app/services/logical_table_builder.py`
- Modify: `tests/core_service/test_logical_table_builder.py`

- [ ] **Step 1: Write the failing regression test for `section_path` preservation**

```python
# tests/core_service/test_logical_table_builder.py
def test_builder_preserves_section_path_for_routing() -> None:
    blocks = [
        _text_block(page_idx=0, text="主营业务收入"),
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 180.0],
            rows=[["分部", "收入"], ["境内", "100"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 1
    assert tables[0].section_path == ["管理层讨论与分析", "主营业务分析"]
```

- [ ] **Step 2: Run the test to verify it fails on the current schema**

Run: `.venv/bin/pytest tests/core_service/test_logical_table_builder.py::test_builder_preserves_section_path_for_routing -q`

Expected: FAIL with `AttributeError: 'LogicalTable' object has no attribute 'section_path'`

- [ ] **Step 3: Extend `LogicalTable` and `LogicalTableBuilder` with `section_path`**

```python
# apps/core_service/app/schemas/logical_table.py
from pydantic import BaseModel, Field


class LogicalTableSegment(BaseModel):
    page_idx: int
    block_index: int
    bbox: list[float]


class LogicalTable(BaseModel):
    logical_table_id: str
    start_page: int
    end_page: int
    header: list[str]
    rows: list[list[str | None]]
    section_path: list[str] = Field(default_factory=list)
    segments: list[LogicalTableSegment] = Field(default_factory=list)
    context_before: list[str] = Field(default_factory=list)
```

```python
# apps/core_service/app/services/logical_table_builder.py
    def _new_logical_table(
        self,
        blocks: list[ArtifactContentBlock],
        index: int,
        block: ArtifactContentBlock,
        header: list[str],
        rows: list[list[str | None]],
    ) -> LogicalTable:
        return LogicalTable(
            logical_table_id=f"logical-table-{block.page_idx}-{index}",
            start_page=block.page_idx,
            end_page=block.page_idx,
            header=header,
            rows=rows,
            section_path=list(self._section_path(block) or ()),
            segments=[
                LogicalTableSegment(
                    page_idx=block.page_idx,
                    block_index=index,
                    bbox=block.bbox,
                )
            ],
            context_before=self._collect_preceding_texts(blocks, index),
        )
```

- [ ] **Step 4: Run the logical table builder regression suite**

Run: `.venv/bin/pytest tests/core_service/test_logical_table_builder.py -q`

Expected: PASS with `9 passed`

- [ ] **Step 5: Commit the routing input bridge**

```bash
git add apps/core_service/app/schemas/logical_table.py apps/core_service/app/services/logical_table_builder.py tests/core_service/test_logical_table_builder.py
git commit -m "feat(router): 保留逻辑表章节路径"
```

## Task 2: Implement Deterministic Table Router

**Files:**
- Create: `apps/core_service/app/schemas/routing.py`
- Create: `apps/core_service/app/services/table_router.py`
- Create: `tests/core_service/test_table_router.py`

- [ ] **Step 1: Write the failing router tests for fast, slow, and not-find decisions**

```python
# tests/core_service/test_table_router.py
from decimal import Decimal

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment
from apps.core_service.app.services.table_router import TableRouter


def _rule(
    *,
    headers: list[str],
    keywords: list[str],
    title_pattern: str | None = None,
) -> TableExtractionRule:
    anchor_rule: dict[str, object] = {
        "logic_match": {
            "required_headers": headers,
            "required_context_keywords": keywords,
        }
    }
    if title_pattern is not None:
        anchor_rule["regex_match"] = {"title_pattern": title_pattern}
    return TableExtractionRule(
        id=3001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule=anchor_rule,
        semantic_anchor_text="主营业务收入 分部 收入",
        min_match_score=Decimal("0.850"),
        is_active="1",
    )


def _logical_table(*, header: list[str], rows: list[list[str]], context_before: list[str]) -> LogicalTable:
    return LogicalTable(
        logical_table_id="lt-1",
        start_page=3,
        end_page=3,
        header=header,
        rows=rows,
        section_path=["管理层讨论与分析", "主营业务分析"],
        segments=[LogicalTableSegment(page_idx=3, block_index=4, bbox=[0.0, 40.0, 300.0, 180.0])],
        context_before=context_before,
    )


def _text_block(*, page_idx: int, text: str) -> ArtifactContentBlock:
    return ArtifactContentBlock(
        type="text",
        page_idx=page_idx,
        bbox=[0.0, 0.0, 300.0, 24.0],
        text=text,
    )


def test_router_returns_fast_track_when_path_and_headers_match() -> None:
    decision = TableRouter().route(
        rule=_rule(headers=["分部", "收入"], keywords=["主营业务"]),
        logical_tables=[
            _logical_table(
                header=["分部", "收入"],
                rows=[["境内", "100"]],
                context_before=["主营业务收入表"],
            )
        ],
        content_blocks=[_text_block(page_idx=3, text="主营业务分析")],
    )

    assert decision.decision == "FAST_TRACK"
    assert decision.matched_table is not None
    assert decision.matched_table.logical_table_id == "lt-1"
    assert decision.best_score >= Decimal("0.850")


def test_router_returns_slow_track_when_section_exists_but_table_score_is_too_low() -> None:
    decision = TableRouter().route(
        rule=_rule(headers=["分部", "营业收入"], keywords=["主营业务"]),
        logical_tables=[
            _logical_table(
                header=["分部", "收入"],
                rows=[["境内", "100"]],
                context_before=["主营业务分析", "公司主营业务收入如下"],
            )
        ],
        content_blocks=[
            _text_block(page_idx=3, text="主营业务分析"),
            _text_block(page_idx=3, text="公司主营业务收入如下。"),
        ],
    )

    assert decision.decision == "SLOW_TRACK"
    assert decision.matched_table is None
    assert "公司主营业务收入如下。" in decision.context_blocks


def test_router_returns_not_find_when_no_section_fingerprint_is_present() -> None:
    decision = TableRouter().route(
        rule=_rule(headers=["分部", "收入"], keywords=["主营业务"]),
        logical_tables=[],
        content_blocks=[_text_block(page_idx=0, text="公司治理")],
    )

    assert decision.decision == "NOT_FIND"
    assert decision.matched_table is None
    assert decision.context_blocks == []
```

- [ ] **Step 2: Run the router tests to verify they fail before implementation**

Run: `.venv/bin/pytest tests/core_service/test_table_router.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.services.table_router'`

- [ ] **Step 3: Add routing schema and deterministic router**

```python
# apps/core_service/app/schemas/routing.py
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from apps.core_service.app.schemas.logical_table import LogicalTable


class RoutingCandidate(BaseModel):
    logical_table: LogicalTable
    score: Decimal
    matched_headers: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    matched_title: str | None = None


class RouteDecision(BaseModel):
    decision: Literal["FAST_TRACK", "SLOW_TRACK", "NOT_FIND"]
    best_score: Decimal = Decimal("0.000")
    matched_path: list[str] = Field(default_factory=list)
    matched_table: LogicalTable | None = None
    context_blocks: list[str] = Field(default_factory=list)
    remark: str
```

```python
# apps/core_service/app/services/table_router.py
import re
from decimal import Decimal

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.logical_table import LogicalTable
from apps.core_service.app.schemas.routing import RouteDecision


class TableRouter:
    def route(
        self,
        *,
        rule: TableExtractionRule,
        logical_tables: list[LogicalTable],
        content_blocks: list[ArtifactContentBlock],
    ) -> RouteDecision:
        section_tables = [
            table
            for table in logical_tables
            if self._path_matches(rule.path_fingerprints, table.section_path)
        ]
        if section_tables:
            best_table = max(
                section_tables,
                key=lambda table: self._candidate_score(rule, table),
            )
            best_score = self._candidate_score(rule, best_table)
            if best_score >= self._threshold(rule):
                return RouteDecision(
                    decision="FAST_TRACK",
                    best_score=best_score,
                    matched_path=best_table.section_path,
                    matched_table=best_table,
                    context_blocks=list(best_table.context_before),
                    remark="Matched logical table by path fingerprint and anchor rules.",
                )
            return RouteDecision(
                decision="SLOW_TRACK",
                best_score=best_score,
                matched_path=best_table.section_path,
                matched_table=None,
                context_blocks=self._section_context(
                    rule=rule,
                    content_blocks=content_blocks,
                    logical_tables=section_tables,
                ),
                remark="Matched section fingerprint but no logical table reached the minimum score.",
            )

        text_only_context = self._text_only_context(rule, content_blocks)
        if text_only_context:
            return RouteDecision(
                decision="SLOW_TRACK",
                best_score=Decimal("0.000"),
                matched_path=list(rule.path_fingerprints),
                matched_table=None,
                context_blocks=text_only_context,
                remark="Matched section heading in text blocks but did not find a standard logical table.",
            )

        return RouteDecision(
            decision="NOT_FIND",
            best_score=Decimal("0.000"),
            matched_path=[],
            matched_table=None,
            context_blocks=[],
            remark="Section fingerprint was not found in the parsed artifact.",
        )

    def _candidate_score(
        self,
        rule: TableExtractionRule,
        table: LogicalTable,
    ) -> Decimal:
        anchor_rule = rule.anchor_rule or {}
        logic_match = anchor_rule.get("logic_match", {})
        regex_match = anchor_rule.get("regex_match", {})
        header_set = {cell for cell in table.header if cell}
        context_text = " ".join([*table.section_path, *table.context_before])
        score = Decimal("0.350")

        required_headers = logic_match.get("required_headers", [])
        if required_headers and all(header in header_set for header in required_headers):
            score += Decimal("0.350")

        required_keywords = logic_match.get("required_context_keywords", [])
        if required_keywords and all(keyword in context_text for keyword in required_keywords):
            score += Decimal("0.150")

        title_pattern = regex_match.get("title_pattern")
        if isinstance(title_pattern, str) and re.search(title_pattern, context_text):
            score += Decimal("0.100")

        if rule.semantic_anchor_text:
            score += self._semantic_overlap_bonus(rule.semantic_anchor_text, context_text)

        return min(score, Decimal("1.000"))

    def _semantic_overlap_bonus(self, anchor_text: str, context_text: str) -> Decimal:
        anchor_tokens = {token for token in anchor_text.split() if token}
        context_tokens = {token for token in context_text.split() if token}
        if not anchor_tokens or not context_tokens:
            return Decimal("0.000")
        overlap = len(anchor_tokens & context_tokens) / len(anchor_tokens)
        return Decimal(str(round(overlap * 0.050, 3)))

    def _threshold(self, rule: TableExtractionRule) -> Decimal:
        return rule.min_match_score or Decimal("0.850")

    def _path_matches(self, fingerprint: list[str], section_path: list[str]) -> bool:
        return tuple(path.strip() for path in fingerprint) == tuple(path.strip() for path in section_path)

    def _section_context(
        self,
        *,
        rule: TableExtractionRule,
        content_blocks: list[ArtifactContentBlock],
        logical_tables: list[LogicalTable],
    ) -> list[str]:
        page_numbers = {
            segment.page_idx
            for table in logical_tables
            for segment in table.segments
        }
        texts = [
            block.text.strip()
            for block in content_blocks
            if block.type == "text"
            and block.text
            and block.page_idx in page_numbers
            and block.text.strip()
        ]
        if texts:
            return texts
        return list(rule.path_fingerprints)

    def _text_only_context(
        self,
        rule: TableExtractionRule,
        content_blocks: list[ArtifactContentBlock],
    ) -> list[str]:
        fingerprints = [item.strip() for item in rule.path_fingerprints if item.strip()]
        return [
            block.text.strip()
            for block in content_blocks
            if block.type == "text"
            and block.text
            and any(fingerprint in block.text for fingerprint in fingerprints)
        ]
```

- [ ] **Step 4: Run the router tests to verify all three decisions pass**

Run: `.venv/bin/pytest tests/core_service/test_table_router.py -q`

Expected: PASS with `3 passed`

- [ ] **Step 5: Commit the routing layer**

```bash
git add apps/core_service/app/schemas/routing.py apps/core_service/app/services/table_router.py tests/core_service/test_table_router.py
git commit -m "feat(router): 增加规则路由决策"
```

## Task 3: Add Fast Track Extraction And Result Upsert

**Files:**
- Create: `apps/core_service/app/schemas/extraction.py`
- Create: `apps/core_service/app/services/fast_track_extractor.py`
- Modify: `apps/core_service/app/repositories/extracted_result_repository.py`
- Create: `tests/core_service/test_fast_track_extractor.py`
- Modify: `tests/core_service/test_extraction_repositories.py`

- [ ] **Step 1: Write the failing tests for fast-track output and result upsert**

```python
# tests/core_service/test_fast_track_extractor.py
from decimal import Decimal

from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment
from apps.core_service.app.schemas.routing import RouteDecision
from apps.core_service.app.services.fast_track_extractor import FastTrackExtractor


def test_fast_track_extractor_builds_success_outcome() -> None:
    decision = RouteDecision(
        decision="FAST_TRACK",
        best_score=Decimal("0.950"),
        matched_path=["管理层讨论与分析", "主营业务分析"],
        matched_table=LogicalTable(
            logical_table_id="lt-1",
            start_page=3,
            end_page=4,
            header=["分部", "收入"],
            rows=[["境内", "100"], ["境外", "80"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
            segments=[
                LogicalTableSegment(page_idx=3, block_index=2, bbox=[0.0, 40.0, 300.0, 180.0]),
                LogicalTableSegment(page_idx=4, block_index=1, bbox=[0.0, 36.0, 300.0, 170.0]),
            ],
            context_before=["主营业务收入表"],
        ),
        context_blocks=["主营业务收入表"],
        remark="Matched logical table by path fingerprint and anchor rules.",
    )

    outcome = FastTrackExtractor().extract(decision=decision)

    assert outcome.data_status == "SUCCESS"
    assert outcome.extraction_route == "FAST_TRACK"
    assert outcome.start_page == 3
    assert outcome.end_page == 4
    assert outcome.table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", "100"], ["境外", "80"]],
    }
    assert outcome.bbox == [
        {"page": 3, "x0": 0.0, "y0": 40.0, "x1": 300.0, "y1": 180.0},
        {"page": 4, "x0": 0.0, "y0": 36.0, "x1": 300.0, "y1": 170.0},
    ]
```

```python
# tests/core_service/test_extraction_repositories.py
from apps.core_service.app.schemas.extraction import ExtractionOutcome


async def test_rule_listing_and_result_upsert(async_session) -> None:
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
    async_session.add(active_rule)
    await async_session.commit()

    rule_repo = TableExtractionRuleRepository()
    result_repo = ExtractedResultRepository()

    active_rules = await rule_repo.list_active_by_doc_type(
        async_session,
        doc_type="ANNUAL_REPORT",
    )
    assert [rule.target_table_code for rule in active_rules] == ["main_business_revenue"]

    outcome = ExtractionOutcome(
        data_status="SUCCESS",
        extraction_route="FAST_TRACK",
        table_data={"headers": ["分部", "收入"], "rows": [["境内", "100"]]},
        start_page=3,
        end_page=3,
        bbox=[{"page": 3, "x0": 0.0, "y0": 40.0, "x1": 300.0, "y1": 180.0}],
        confidence_score=Decimal("95.00"),
        needs_review="0",
        remark="Rule matched logical table with score 0.950.",
    )

    result = await result_repo.upsert_result(
        async_session,
        result_id=9001,
        task_id=1001,
        rule=active_rule,
        outcome=outcome,
    )
    await async_session.commit()

    assert result.data_status == "SUCCESS"
    assert result.extraction_route == "FAST_TRACK"
    assert result.table_data == {"headers": ["分部", "收入"], "rows": [["境内", "100"]]}
    assert result.start_page == 3
    assert result.end_page == 3
```

- [ ] **Step 2: Run the fast-track tests to verify they fail before implementation**

Run: `.venv/bin/pytest tests/core_service/test_fast_track_extractor.py tests/core_service/test_extraction_repositories.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.services.fast_track_extractor'`

- [ ] **Step 3: Add `ExtractionOutcome`, `FastTrackExtractor`, and repository upsert**

```python
# apps/core_service/app/schemas/extraction.py
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ExtractionOutcome(BaseModel):
    data_status: Literal["SUCCESS", "NOT_DISCLOSED", "NOT_FIND"]
    extraction_route: Literal["FAST_TRACK", "SLOW_TRACK"] | None = None
    table_data: dict[str, object] | None = None
    start_page: int | None = None
    end_page: int | None = None
    bbox: list[dict[str, int | float]] | None = None
    confidence_score: Decimal
    needs_review: str = "0"
    remark: str | None = None
    unit: str | None = None
    currency: str | None = None
```

```python
# apps/core_service/app/services/fast_track_extractor.py
from decimal import Decimal

from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.routing import RouteDecision


class FastTrackExtractor:
    def extract(self, *, decision: RouteDecision) -> ExtractionOutcome:
        if decision.matched_table is None:
            raise ValueError("FAST_TRACK decision requires a matched logical table.")

        bbox = [
            {
                "page": segment.page_idx,
                "x0": segment.bbox[0],
                "y0": segment.bbox[1],
                "x1": segment.bbox[2],
                "y1": segment.bbox[3],
            }
            for segment in decision.matched_table.segments
        ]
        return ExtractionOutcome(
            data_status="SUCCESS",
            extraction_route="FAST_TRACK",
            table_data={
                "headers": list(decision.matched_table.header),
                "rows": list(decision.matched_table.rows),
            },
            start_page=decision.matched_table.start_page,
            end_page=decision.matched_table.end_page,
            bbox=bbox,
            confidence_score=Decimal("95.00"),
            needs_review="0",
            remark=f"Rule matched logical table with score {decision.best_score:.3f}.",
        )
```

```python
# apps/core_service/app/repositories/extracted_result_repository.py
from apps.core_service.app.schemas.extraction import ExtractionOutcome


class ExtractedResultRepository:
    async def upsert_result(
        self,
        session: AsyncSession,
        *,
        result_id: int,
        task_id: int,
        rule: TableExtractionRule,
        outcome: ExtractionOutcome,
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
                data_status=outcome.data_status,
                confidence_score=outcome.confidence_score,
                needs_review=outcome.needs_review,
            )
            session.add(existing)

        existing.unit = outcome.unit
        existing.currency = outcome.currency
        existing.extraction_route = outcome.extraction_route
        existing.table_data = outcome.table_data
        existing.fix_table_data = None
        existing.start_page = outcome.start_page
        existing.end_page = outcome.end_page
        existing.bbox = outcome.bbox
        existing.remark = outcome.remark
        existing.data_status = outcome.data_status
        existing.confidence_score = outcome.confidence_score
        existing.needs_review = outcome.needs_review
        existing.update_time = datetime.now(UTC)
        await session.flush()
        await session.refresh(existing)
        return existing
```

- [ ] **Step 4: Run the fast-track and repository tests**

Run: `.venv/bin/pytest tests/core_service/test_fast_track_extractor.py tests/core_service/test_extraction_repositories.py -q`

Expected: PASS with `2 passed`

- [ ] **Step 5: Commit the fast-track persistence layer**

```bash
git add apps/core_service/app/schemas/extraction.py apps/core_service/app/services/fast_track_extractor.py apps/core_service/app/repositories/extracted_result_repository.py tests/core_service/test_fast_track_extractor.py tests/core_service/test_extraction_repositories.py
git commit -m "feat(extractor): 增加规则快车道结果"
```

## Task 4: Add Pluggable LLM Fallback Client

**Files:**
- Modify: `apps/core_service/app/errors.py`
- Create: `apps/core_service/app/clients/llm_fallback.py`
- Modify: `apps/core_service/app/settings.py`
- Modify: `apps/core_service/app/extractor_main.py`
- Modify: `tests/conftest.py`
- Create: `tests/core_service/test_llm_fallback_client.py`

- [ ] **Step 1: Write the failing tests for disabled fallback and HTTP parsing**

```python
# tests/core_service/test_llm_fallback_client.py
import json
from decimal import Decimal

import httpx
import pytest

from apps.core_service.app.clients.llm_fallback import (
    DisabledLLMFallbackClient,
    HttpLLMFallbackClient,
)
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.routing import RouteDecision


def _rule() -> TableExtractionRule:
    return TableExtractionRule(
        id=3001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule={},
        semantic_anchor_text="主营业务收入",
        min_match_score=Decimal("0.850"),
        is_active="1",
    )


@pytest.mark.asyncio
async def test_disabled_fallback_returns_not_disclosed() -> None:
    client = DisabledLLMFallbackClient()

    outcome = await client.extract(
        rule=_rule(),
        decision=RouteDecision(
            decision="SLOW_TRACK",
            matched_path=["管理层讨论与分析", "主营业务分析"],
            context_blocks=["主营业务分析", "本期未披露主营业务收入明细。"],
            remark="Matched section fingerprint but no logical table reached the minimum score.",
        ),
    )

    assert outcome.data_status == "NOT_DISCLOSED"
    assert outcome.extraction_route == "SLOW_TRACK"


@pytest.mark.asyncio
async def test_http_fallback_parses_success_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["target_table_code"] == "main_business_revenue"
        assert payload["context_blocks"] == ["主营业务分析", "公司主营业务收入如下。"]
        return httpx.Response(
            200,
            json={
                "data_status": "SUCCESS",
                "table_data": {
                    "headers": ["分部", "收入"],
                    "rows": [["境内", "100"]],
                },
                "remark": "Extracted from fallback context.",
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = HttpLLMFallbackClient(
        endpoint="http://llm.test/extract",
        model_name="fallback-test",
        timeout_seconds=30.0,
        http_client=http_client,
    )

    outcome = await client.extract(
        rule=_rule(),
        decision=RouteDecision(
            decision="SLOW_TRACK",
            matched_path=["管理层讨论与分析", "主营业务分析"],
            context_blocks=["主营业务分析", "公司主营业务收入如下。"],
            remark="Matched section fingerprint but no logical table reached the minimum score.",
        ),
    )

    assert outcome.data_status == "SUCCESS"
    assert outcome.extraction_route == "SLOW_TRACK"
    assert outcome.table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", "100"]],
    }
```

- [ ] **Step 2: Run the fallback client tests to verify they fail before implementation**

Run: `.venv/bin/pytest tests/core_service/test_llm_fallback_client.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.clients.llm_fallback'`

- [ ] **Step 3: Add fallback client implementations, config, and fake test double**

```python
# apps/core_service/app/errors.py
class LLMFallbackClientError(DependencyBoundaryError):
    pass
```

```python
# apps/core_service/app/clients/llm_fallback.py
from decimal import Decimal

import httpx
from pydantic import BaseModel, ValidationError

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.errors import LLMFallbackClientError
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.routing import RouteDecision


class LLMFallbackResponse(BaseModel):
    data_status: str
    table_data: dict[str, object] | None = None
    remark: str | None = None


class LLMFallbackClient:
    async def extract(
        self,
        *,
        rule: TableExtractionRule,
        decision: RouteDecision,
    ) -> ExtractionOutcome:
        raise NotImplementedError


class DisabledLLMFallbackClient(LLMFallbackClient):
    async def extract(
        self,
        *,
        rule: TableExtractionRule,
        decision: RouteDecision,
    ) -> ExtractionOutcome:
        del rule, decision
        return ExtractionOutcome(
            data_status="NOT_DISCLOSED",
            extraction_route="SLOW_TRACK",
            confidence_score=Decimal("88.00"),
            needs_review="0",
            remark="LLM fallback disabled; matched section did not contain a standard table.",
        )


class HttpLLMFallbackClient(LLMFallbackClient):
    def __init__(
        self,
        *,
        endpoint: str,
        model_name: str,
        timeout_seconds: float,
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._model_name = model_name
        self._api_key = api_key
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def extract(
        self,
        *,
        rule: TableExtractionRule,
        decision: RouteDecision,
    ) -> ExtractionOutcome:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self._model_name,
            "target_table_code": rule.target_table_code,
            "target_table_name": rule.target_table_name,
            "context_blocks": decision.context_blocks,
            "matched_path": decision.matched_path,
        }
        try:
            response = await self._http_client.post(
                self._endpoint,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            parsed = LLMFallbackResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError) as exc:
            raise LLMFallbackClientError(
                "Failed to call LLM fallback endpoint.",
                reason=exc.__class__.__name__,
            ) from exc

        return ExtractionOutcome(
            data_status="SUCCESS" if parsed.data_status == "SUCCESS" else "NOT_DISCLOSED",
            extraction_route="SLOW_TRACK",
            table_data=parsed.table_data,
            confidence_score=Decimal("88.00"),
            needs_review="0",
            remark=parsed.remark or "LLM fallback completed.",
        )

    async def dispose(self) -> None:
        if self._owns_client:
            await self._http_client.aclose()
```

```python
# apps/core_service/app/settings.py
class Settings(BaseSettings):
    llm_fallback_enabled: bool = False
    llm_fallback_url: str = "http://127.0.0.1:18080/extract"
    llm_fallback_model: str = "fallback-default"
    llm_fallback_api_key: str | None = None
    llm_fallback_timeout_seconds: float = Field(default=30.0, gt=0)
```

```python
# apps/core_service/app/extractor_main.py
from apps.core_service.app.clients.llm_fallback import (
    DisabledLLMFallbackClient,
    HttpLLMFallbackClient,
)


async def run(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
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
    llm_fallback_client = (
        HttpLLMFallbackClient(
            endpoint=app_settings.llm_fallback_url,
            model_name=app_settings.llm_fallback_model,
            api_key=app_settings.llm_fallback_api_key,
            timeout_seconds=app_settings.llm_fallback_timeout_seconds,
        )
        if app_settings.llm_fallback_enabled
        else DisabledLLMFallbackClient()
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
        llm_fallback_client=llm_fallback_client,
    )
    try:
        while True:
            await worker.process_next_message(timeout_seconds=5)
    finally:
        if hasattr(llm_fallback_client, "dispose"):
            await llm_fallback_client.dispose()
        await object_storage_client.dispose()
        await queue_client.dispose()
        await database_client.dispose()
```

```python
# tests/conftest.py
from apps.core_service.app.clients.llm_fallback import LLMFallbackClient
from apps.core_service.app.errors import LLMFallbackClientError
from apps.core_service.app.schemas.extraction import ExtractionOutcome


class FakeExtractedResultRepository:
    def __init__(self) -> None:
        self.rows: list[ExtractedResult] = []

    async def upsert_result(
        self,
        session,
        *,
        result_id: int,
        task_id: int,
        rule: TableExtractionRule,
        outcome: ExtractionOutcome,
    ) -> ExtractedResult:
        del session
        for row in self.rows:
            if row.task_id == task_id and row.rule_id == rule.id:
                row.data_status = outcome.data_status
                row.extraction_route = outcome.extraction_route
                row.table_data = outcome.table_data
                row.start_page = outcome.start_page
                row.end_page = outcome.end_page
                row.bbox = outcome.bbox
                row.confidence_score = outcome.confidence_score
                row.needs_review = outcome.needs_review
                row.remark = outcome.remark
                row.update_time = _utc_now()
                return row

        row = ExtractedResult(
            id=result_id,
            task_id=task_id,
            rule_id=rule.id,
            target_table_code=rule.target_table_code,
            unit=outcome.unit,
            currency=outcome.currency,
            extraction_route=outcome.extraction_route,
            data_status=outcome.data_status,
            table_data=outcome.table_data,
            fix_table_data=None,
            start_page=outcome.start_page,
            end_page=outcome.end_page,
            bbox=outcome.bbox,
            confidence_score=outcome.confidence_score,
            needs_review=outcome.needs_review,
            remark=outcome.remark,
            create_time=datetime.now(UTC),
            update_time=datetime.now(UTC),
        )
        self.rows.append(row)
        return row


class FakeLLMFallbackClient(LLMFallbackClient):
    def __init__(self) -> None:
        self.responses: list[ExtractionOutcome] = []
        self.raise_error = False
        self.calls: list[dict[str, object]] = []

    async def extract(self, *, rule, decision) -> ExtractionOutcome:
        self.calls.append(
            {
                "target_table_code": rule.target_table_code,
                "matched_path": decision.matched_path,
                "context_blocks": list(decision.context_blocks),
            }
        )
        if self.raise_error:
            raise LLMFallbackClientError(
                "Failed to call LLM fallback endpoint.",
                reason="FakeFallbackFailure",
            )
        if self.responses:
            return self.responses.pop(0)
        return ExtractionOutcome(
            data_status="NOT_DISCLOSED",
            extraction_route="SLOW_TRACK",
            confidence_score=Decimal("88.00"),
            needs_review="0",
            remark="Fake fallback defaulted to NOT_DISCLOSED.",
        )


@pytest.fixture
async def test_app() -> AsyncIterator:
    database_client = FakeDatabaseClient()
    object_storage_client = FakeObjectStorageClient()
    queue_client = FakeQueueClient()
    task_repository = FakeTaskRepository()
    rule_repository = FakeTableExtractionRuleRepository()
    result_repository = FakeExtractedResultRepository()
    llm_fallback_client = FakeLLMFallbackClient()
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///unused.db",
            task_id_node_id=7,
            minio_bucket=object_storage_client.bucket_name,
            parser_queue_name=queue_client.queue_name,
            extractor_queue_name=queue_client.extractor_queue_name,
        ),
        database_client=database_client,
        object_storage_client=object_storage_client,
        queue_client=queue_client,
    )
    app.state.task_repository = task_repository
    app.state.rule_repository = rule_repository
    app.state.result_repository = result_repository
    app.state.llm_fallback_client = llm_fallback_client
```

- [ ] **Step 4: Run the fallback client tests**

Run: `.venv/bin/pytest tests/core_service/test_llm_fallback_client.py -q`

Expected: PASS with `2 passed`

- [ ] **Step 5: Commit the slow-track client layer**

```bash
git add apps/core_service/app/errors.py apps/core_service/app/clients/llm_fallback.py apps/core_service/app/settings.py apps/core_service/app/extractor_main.py tests/conftest.py tests/core_service/test_llm_fallback_client.py
git commit -m "feat(llm): 接入慢车道兜底客户端"
```

## Task 5: Wire Router And Dual-Route Extraction Into `ExtractorWorker`

**Files:**
- Modify: `apps/core_service/app/services/extractor_worker.py`
- Modify: `tests/core_service/test_extractor_worker.py`

- [ ] **Step 1: Write the failing worker tests for fast-track, slow-track, and not-find outcomes**

```python
# tests/core_service/test_extractor_worker.py
from apps.core_service.app.schemas.extraction import ExtractionOutcome


async def test_extractor_worker_persists_fast_track_results(async_client, test_app) -> None:
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
            semantic_anchor_text="主营业务收入 分部 收入",
            min_match_score=Decimal("0.850"),
            is_active="1",
        )
    ]

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].data_status == "SUCCESS"
    assert rows[0].extraction_route == "FAST_TRACK"
    assert rows[0].table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", "100"], ["境外", "80"], ["其他", "20"]],
    }


async def test_extractor_worker_uses_llm_fallback_when_section_matches_without_standard_table(
    async_client, test_app
) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("extract.pdf", b"%PDF-1.7\nextract", "application/pdf")},
    )
    payload = response.json()
    task_id = int(payload["task_id"])
    bucket = test_app.state.object_storage_client.bucket_name
    content_key = build_content_list_object_key(task_id)

    await test_app.state.object_storage_client.upload_bytes(
        bucket=bucket,
        object_key=content_key,
        data=json.dumps(
            [
                {"type": "text", "page_idx": 0, "bbox": [0.0, 0.0, 200.0, 20.0], "text": "主营业务分析"},
                {"type": "text", "page_idx": 0, "bbox": [0.0, 20.0, 200.0, 40.0], "text": "公司主营业务收入如下。"},
                {
                    "type": "table",
                    "page_idx": 0,
                    "bbox": [0.0, 40.0, 300.0, 140.0],
                    "table_body": [["项目", "金额"], ["主营业务", "100"]],
                    "metadata": {"section_path": ["管理层讨论与分析", "主营业务分析"]},
                },
            ],
            ensure_ascii=True,
        ).encode("utf-8"),
        content_type="application/json",
    )
    test_app.state.queue_client.extractor_messages.append(
        ExtractorTaskMessage(
            task_id=payload["task_id"],
            doc_type="ANNUAL_REPORT",
            bucket=bucket,
            content_list_object_key=content_key,
        )
    )
    test_app.state.rule_repository.rules = [
        TableExtractionRule(
            id=3001,
            doc_type="ANNUAL_REPORT",
            target_table_code="main_business_revenue",
            target_table_name="主营业务收入",
            path_fingerprints=["管理层讨论与分析", "主营业务分析"],
            anchor_rule={"logic_match": {"required_headers": ["分部", "收入"]}},
            semantic_anchor_text="主营业务收入 分部 收入",
            min_match_score=Decimal("0.850"),
            is_active="1",
        )
    ]
    test_app.state.llm_fallback_client.responses.append(
        ExtractionOutcome(
            data_status="SUCCESS",
            extraction_route="SLOW_TRACK",
            table_data={"headers": ["分部", "收入"], "rows": [["主营业务", "100"]]},
            confidence_score=Decimal("88.00"),
            needs_review="0",
            remark="Extracted from fallback context.",
        )
    )

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].data_status == "SUCCESS"
    assert rows[0].extraction_route == "SLOW_TRACK"
    assert rows[0].table_data == {
        "headers": ["分部", "收入"],
        "rows": [["主营业务", "100"]],
    }
    assert test_app.state.llm_fallback_client.calls[0]["target_table_code"] == "main_business_revenue"


async def test_extractor_worker_marks_not_find_when_section_is_missing(
    async_client, test_app
) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("extract.pdf", b"%PDF-1.7\nextract", "application/pdf")},
    )
    payload = response.json()
    task_id = int(payload["task_id"])
    bucket = test_app.state.object_storage_client.bucket_name
    content_key = build_content_list_object_key(task_id)

    await test_app.state.object_storage_client.upload_bytes(
        bucket=bucket,
        object_key=content_key,
        data=json.dumps(
            [{"type": "text", "page_idx": 0, "bbox": [0.0, 0.0, 200.0, 20.0], "text": "公司治理"}],
            ensure_ascii=True,
        ).encode("utf-8"),
        content_type="application/json",
    )
    test_app.state.queue_client.extractor_messages.append(
        ExtractorTaskMessage(
            task_id=payload["task_id"],
            doc_type="ANNUAL_REPORT",
            bucket=bucket,
            content_list_object_key=content_key,
        )
    )
    test_app.state.rule_repository.rules = [
        TableExtractionRule(
            id=3001,
            doc_type="ANNUAL_REPORT",
            target_table_code="main_business_revenue",
            target_table_name="主营业务收入",
            path_fingerprints=["管理层讨论与分析", "主营业务分析"],
            anchor_rule={"logic_match": {"required_headers": ["分部", "收入"]}},
            semantic_anchor_text="主营业务收入 分部 收入",
            min_match_score=Decimal("0.850"),
            is_active="1",
        )
    ]

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].data_status == "NOT_FIND"
    assert rows[0].extraction_route is None
```

- [ ] **Step 2: Run the worker suite to verify the new behavior is still missing**

Run: `.venv/bin/pytest tests/core_service/test_extractor_worker.py -q`

Expected: FAIL because the current worker still writes placeholder `NOT_FIND` results and never calls fallback.

- [ ] **Step 3: Integrate router, fast track, fallback, and real result persistence into the worker**

```python
# apps/core_service/app/services/extractor_worker.py
from decimal import Decimal

from apps.core_service.app.clients.llm_fallback import (
    DisabledLLMFallbackClient,
    LLMFallbackClient,
)
from apps.core_service.app.errors import LLMFallbackClientError
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.routing import RouteDecision
from apps.core_service.app.services.fast_track_extractor import FastTrackExtractor
from apps.core_service.app.services.table_router import TableRouter


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
        logical_table_builder: LogicalTableBuilder | None = None,
        table_router: TableRouter | None = None,
        fast_track_extractor: FastTrackExtractor | None = None,
        llm_fallback_client: LLMFallbackClient | None = None,
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
        self._logical_table_builder = logical_table_builder or LogicalTableBuilder()
        self._table_router = table_router or TableRouter()
        self._fast_track_extractor = fast_track_extractor or FastTrackExtractor()
        self._llm_fallback_client = llm_fallback_client or DisabledLLMFallbackClient()
        self._trace_id_factory = trace_id_factory or (lambda: uuid4().hex)

    async def process_next_message(self, *, timeout_seconds: int) -> bool:
        logical_tables = self._logical_table_builder.build(content_blocks)
        async with self._session_factory() as session:
            try:
                rules = await self._rule_repository.list_active_by_doc_type(
                    session,
                    doc_type=message.doc_type,
                )
                for rule in rules:
                    decision = self._table_router.route(
                        rule=rule,
                        logical_tables=logical_tables,
                        content_blocks=content_blocks,
                    )
                    outcome = await self._build_outcome(rule=rule, decision=decision)
                    await self._result_repository.upsert_result(
                        session,
                        result_id=self._id_generator.next_id(),
                        task_id=task.id,
                        rule=rule,
                        outcome=outcome,
                    )

                await self._task_repository.set_status(
                    session,
                    task,
                    status=TaskStatus.COMPLETED,
                    remark=None if rules else "No active extraction rules configured.",
                )
                await session.commit()
            except (SQLAlchemyError, LLMFallbackClientError) as exc:
                await session.rollback()
                if isinstance(exc, LLMFallbackClientError):
                    await self._mark_failed(
                        int(message.task_id),
                        remark="Failed to call LLM fallback endpoint.",
                        trace_id=trace_id,
                        code="LLM_FALLBACK_UNAVAILABLE",
                        reason=exc.reason,
                        bucket=message.bucket,
                        object_key=logical_tables_object_key,
                    )
                    return True
                await self._cleanup_logical_tables_artifact(
                    bucket=message.bucket,
                    object_key=logical_tables_object_key,
                    task_id=message.task_id,
                    trace_id=trace_id,
                )
                self._logger.error(
                    "Failed to persist extractor result state.",
                    extra={
                        "service": "core_service",
                        "phase": "extract_complete",
                        "event": "extract_failed",
                        "task_id": message.task_id,
                        "trace_id": trace_id,
                        "bucket": message.bucket,
                        "object_key": logical_tables_object_key,
                        "code": "DATABASE_UNAVAILABLE",
                        "reason": exc.__class__.__name__,
                    },
                )
                return True

    async def _build_outcome(
        self,
        *,
        rule: TableExtractionRule,
        decision: RouteDecision,
    ) -> ExtractionOutcome:
        if decision.decision == "FAST_TRACK":
            return self._fast_track_extractor.extract(decision=decision)
        if decision.decision == "SLOW_TRACK":
            return await self._llm_fallback_client.extract(rule=rule, decision=decision)
        return ExtractionOutcome(
            data_status="NOT_FIND",
            extraction_route=None,
            confidence_score=Decimal("100.00"),
            needs_review="0",
            remark=decision.remark,
        )
```

```python
# tests/core_service/test_extractor_worker.py
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
        llm_fallback_client=test_app.state.llm_fallback_client,
    )
```

- [ ] **Step 4: Run the worker regression suite**

Run: `.venv/bin/pytest tests/core_service/test_extractor_worker.py -q`

Expected: PASS with `8 passed`

- [ ] **Step 5: Commit the integrated Phase 3 worker flow**

```bash
git add apps/core_service/app/services/extractor_worker.py tests/core_service/test_extractor_worker.py
git commit -m "feat(worker): 接入双路提取编排"
```

## Completion Verification

- [ ] **Step 1: Run the full repository test suite**

Run: `.venv/bin/pytest -q`

Expected: PASS with `37 passed`

- [ ] **Step 2: Confirm the diff is limited to Phase 3 routing files**

Run: `git diff --stat HEAD~5..HEAD`

Expected: only the files listed in `File Structure` plus no unexpected root config, migration, or dependency changes

## Self-Review

### Spec Coverage

- `path_fingerprints` 宏观路由：Task 1 + Task 2
- `anchor_rule.logic_match` / `regex_match`：Task 2
- `semantic_anchor_text` 参与得分：Task 2
- `FAST_TRACK` 标准表提取：Task 3 + Task 5
- `SLOW_TRACK` LLM fallback：Task 4 + Task 5
- `NOT_FIND`：Task 2 + Task 5
- `t_extracted_result` 写回：Task 3 + Task 5

### Intentional Deferrals

- `pgvector` / embedding / 向量召回：未纳入本计划，避免在 parser contract 仍是 skeleton 的阶段引入高耦合基础设施。
- `t_document_toc`：未纳入本计划，当前没有稳定标题树 contract，先使用 `section_path + text block` 内存上下文。
- 单位、币种、评分扣分、review queue：保留到下一阶段计划，避免把 Phase 3 和 Phase 4/5/6 混在一起。

### Placeholder Scan

- 本计划没有使用 `TODO`、`TBD`、`implement later`。
- 每个 task 都给出了精确文件路径、测试代码、命令和预期结果。
- 所有后续步骤引用的类型名保持一致：`RouteDecision`、`ExtractionOutcome`、`FastTrackExtractor`、`LLMFallbackClient`。
