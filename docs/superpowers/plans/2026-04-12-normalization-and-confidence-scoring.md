# Normalization And Confidence Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已完成的 Phase 3 路由与双路提取基线上，补齐 Phase 4/5 的核心落地能力：单位/币种归一化、`0/null/NOT_DISCLOSED/NOT_FIND` 语义统一、`confidence_score` 计算，以及任务级 `COMPLETED | PENDING_REVIEW` 汇总。

**Architecture:** 保持 `parser_service -> extractor_queue -> core extractor worker` 主链路不变，不新增数据库表、不引入 review queue 或前端接口。本阶段在 Core Service 内新增“结果后处理”层：`ExtractorWorker` 先得到原始 `ExtractionOutcome`，再依次执行 `ExtractionNormalizer`、`ConfidenceScorer`、`TaskStatusEvaluator`，最后把最终结果写回 `t_extracted_result`，并据此决定任务状态。

**Tech Stack:** Python 3.13, Pydantic v2, SQLAlchemy 2.x, FastAPI, pytest

---

## Requirement And Design Comparison

已对齐的部分：

- `design.md` Phase 3 已经落地到当前仓库：`TableRouter` 能输出 `FAST_TRACK | SLOW_TRACK | NOT_FIND`，`ExtractorWorker` 能按规则写回 `t_extracted_result`。
- `t_extracted_result` 已经有 Phase 4/5 需要的持久化字段：`unit`、`currency`、`confidence_score`、`needs_review`、`remark`、`fix_table_data`。
- `tests/core_service/test_extractor_worker.py` 已经覆盖快车道、慢车道、`NOT_FIND`、artifact 失败路径和 fallback 失败路径，适合继续扩展为归一化与评分回归。

当前缺口：

- `apps/core_service/app/services/extractor_worker.py` 还没有归一化阶段，快车道和慢车道结果都直接落库，`unit/currency` 始终为空。
- `apps/core_service/app/services/fast_track_extractor.py`、`apps/core_service/app/clients/llm_fallback.py` 当前写入的 `confidence_score` 仍是占位值，尚未体现 Phase 5 的评分规则。
- 任务状态仍然固定写成 `COMPLETED`，没有根据结果分数切换到 `PENDING_REVIEW`。
- `requirement.md` 3.4 里定义的 `0.00` / `null` / `"NOT_DISCLOSED"` / `"NOT_FIND"` 语义分层还没有体现在结果后处理里。

本计划的设计决策：

- 本阶段只实现“主链路必需”的后处理：单位/币种提取、空值语义转换、分数计算、任务级 review gate。`design.md` 提到的“可插拔 Python 清洗脚本”拆到下一份计划，避免把插件注册机制和主链路评分绑在一起。
- 不改数据库 schema。当前表结构足够承载归一化结果和 review 标记，重点放在服务层编排与测试覆盖。
- 单位/币种先收敛到当前需求中最确定的归一化枚举值：`CNY_YUAN`、`CNY_TEN_THOUSAND`、`CNY`。更复杂的多币种扩展保留到后续需求明确后再做。
- 评分规则采用设计稿的最小闭环：基础 100 分；慢车道扣 15 分；`SUCCESS` 结果若无法识别单位再扣 10 分；低于 85 分标记 `needs_review="1"` 并把任务状态切到 `PENDING_REVIEW`。

## Scope Check

`requirement.md` 的 Phase 4/5 还包含“策略注册脚本”和“人工复核队列联动”，但那两块已经是独立子系统，不适合继续塞进这一份计划。本计划只覆盖：

1. 表格数据里的 `-` / 空白 / `0` 归一化
2. 从表格附近文本和慢车道上下文中提取 `unit/currency`
3. `confidence_score` 和 `needs_review`
4. `TaskStatus.COMPLETED | TaskStatus.PENDING_REVIEW` 汇总

本计划明确不做：

- 可插拔后处理脚本注册与执行
- review queue、前端人工复核接口
- 向量相似度扣分细化
- 更多币种和单位枚举扩展

## File Structure

本计划只创建或修改下面这些文件：

- Create: `apps/core_service/app/schemas/normalization.py`
  定义本阶段收敛的单位/币种规范值。
- Modify: `apps/core_service/app/schemas/extraction.py`
  让 `ExtractionOutcome.unit/currency` 直接使用规范值类型。
- Create: `apps/core_service/app/services/extraction_normalizer.py`
  负责从上下文提取单位/币种，并把表格里的 `-` / 空白 / `0` 统一成财务语义结果。
- Create: `apps/core_service/app/services/confidence_scorer.py`
  负责把原始 outcome 转成最终 `confidence_score` 和 `needs_review`。
- Create: `apps/core_service/app/services/task_status_evaluator.py`
  根据所有结果决定任务是 `COMPLETED` 还是 `PENDING_REVIEW`。
- Modify: `apps/core_service/app/services/extractor_worker.py`
  接入 normalizer、scorer、status evaluator，并在落库前统一后处理。
- Create: `tests/core_service/test_extraction_normalizer.py`
  覆盖单位提取和空值语义归一化。
- Create: `tests/core_service/test_confidence_scorer.py`
  覆盖评分规则和任务级状态评估。
- Modify: `tests/core_service/test_extractor_worker.py`
  把现有 worker 回归升级为归一化与评分后的最终行为验证。

## Preflight

- [ ] **Step 1: Verify the current Phase 3 core baseline**

Run: `.venv/bin/python -m pytest tests/core_service/test_extractor_worker.py tests/core_service/test_llm_fallback_client.py -q`

Expected: PASS with `10 passed`

- [ ] **Step 2: Verify the remaining core extractor baseline**

Run: `.venv/bin/python -m pytest tests/core_service/test_extraction_repositories.py tests/core_service/test_fast_track_extractor.py tests/core_service/test_table_router.py tests/core_service/test_logical_table_builder.py -q`

Expected: PASS with `15 passed`

- [ ] **Step 3: Verify the repository baseline before Phase 4/5 work**

Run: `.venv/bin/python -m pytest tests -q`

Expected: PASS with `38 passed`

## Task 1: Add Extraction Normalizer And Normalized Metadata Types

**Files:**
- Create: `apps/core_service/app/schemas/normalization.py`
- Modify: `apps/core_service/app/schemas/extraction.py`
- Create: `apps/core_service/app/services/extraction_normalizer.py`
- Create: `tests/core_service/test_extraction_normalizer.py`

- [ ] **Step 1: Write the failing normalization tests**

```python
# tests/core_service/test_extraction_normalizer.py
from decimal import Decimal

from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment
from apps.core_service.app.schemas.routing import RouteDecision
from apps.core_service.app.services.extraction_normalizer import ExtractionNormalizer


def _text_block(*, page_idx: int, text: str) -> ArtifactContentBlock:
    return ArtifactContentBlock(
        type="text",
        page_idx=page_idx,
        bbox=[0.0, 0.0, 300.0, 24.0],
        text=text,
    )


def test_normalizer_extracts_unit_currency_and_financial_null_semantics() -> None:
    decision = RouteDecision(
        decision="FAST_TRACK",
        matched_path=["管理层讨论与分析", "主营业务分析"],
        matched_table=LogicalTable(
            logical_table_id="lt-1",
            start_page=3,
            end_page=3,
            header=["分部", "收入"],
            rows=[["境内", "-"], ["境外", "0"], ["其他", "  "]],
            section_path=["管理层讨论与分析", "主营业务分析"],
            segments=[
                LogicalTableSegment(
                    page_idx=3,
                    block_index=2,
                    bbox=[0.0, 40.0, 300.0, 180.0],
                )
            ],
            context_before=["主营业务收入表"],
        ),
        context_blocks=["主营业务收入表"],
        remark="Matched logical table by path fingerprint and anchor rules.",
    )
    outcome = ExtractionOutcome(
        data_status="SUCCESS",
        extraction_route="FAST_TRACK",
        table_data={
            "headers": ["分部", "收入"],
            "rows": [["境内", "-"], ["境外", "0"], ["其他", "  "]],
        },
        start_page=3,
        end_page=3,
        bbox=[{"page": 3, "x0": 0.0, "y0": 40.0, "x1": 300.0, "y1": 180.0}],
        confidence_score=Decimal("95.00"),
        needs_review="0",
        remark="raw fast track outcome",
    )

    normalized = ExtractionNormalizer().normalize(
        outcome=outcome,
        decision=decision,
        content_blocks=[
            _text_block(page_idx=3, text="主营业务收入表"),
            _text_block(page_idx=3, text="单位：人民币万元"),
        ],
    )

    assert normalized.unit == "CNY_TEN_THOUSAND"
    assert normalized.currency == "CNY"
    assert normalized.table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", None], ["境外", "0.00"], ["其他", None]],
    }


def test_normalizer_keeps_not_disclosed_without_inventing_metadata() -> None:
    decision = RouteDecision(
        decision="SLOW_TRACK",
        matched_path=["管理层讨论与分析", "主营业务分析"],
        matched_table=None,
        context_blocks=["主营业务分析", "本期未披露主营业务收入明细。"],
        remark="Matched section fingerprint but no logical table reached the minimum score.",
    )
    outcome = ExtractionOutcome(
        data_status="NOT_DISCLOSED",
        extraction_route="SLOW_TRACK",
        table_data=None,
        confidence_score=Decimal("88.00"),
        needs_review="0",
        remark="fallback returned not disclosed",
    )

    normalized = ExtractionNormalizer().normalize(
        outcome=outcome,
        decision=decision,
        content_blocks=[_text_block(page_idx=3, text="本期未披露主营业务收入明细。")],
    )

    assert normalized.data_status == "NOT_DISCLOSED"
    assert normalized.unit is None
    assert normalized.currency is None
    assert normalized.table_data is None
```

- [ ] **Step 2: Run the normalization tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core_service/test_extraction_normalizer.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.services.extraction_normalizer'`

- [ ] **Step 3: Add normalized metadata schema and extraction normalizer**

```python
# apps/core_service/app/schemas/normalization.py
from typing import Literal


NormalizedUnit = Literal["CNY_YUAN", "CNY_TEN_THOUSAND"]
NormalizedCurrency = Literal["CNY"]
```

```python
# apps/core_service/app/schemas/extraction.py
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from apps.core_service.app.schemas.normalization import (
    NormalizedCurrency,
    NormalizedUnit,
)


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
    unit: NormalizedUnit | None = None
    currency: NormalizedCurrency | None = None
```

```python
# apps/core_service/app/services/extraction_normalizer.py
import re

from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.routing import RouteDecision


class ExtractionNormalizer:
    _UNIT_PATTERNS: tuple[tuple[re.Pattern[str], tuple[str, str]], ...] = (
        (re.compile(r"人民币万元"), ("CNY_TEN_THOUSAND", "CNY")),
        (re.compile(r"人民币元"), ("CNY_YUAN", "CNY")),
        (re.compile(r"单位[:：]\\s*元"), ("CNY_YUAN", "CNY")),
    )

    def normalize(
        self,
        *,
        outcome: ExtractionOutcome,
        decision: RouteDecision,
        content_blocks: list[ArtifactContentBlock],
    ) -> ExtractionOutcome:
        normalized_table_data = self._normalize_table_data(outcome.table_data)
        unit, currency = self._extract_unit_currency(
            decision=decision,
            content_blocks=content_blocks,
        )
        return outcome.model_copy(
            update={
                "table_data": normalized_table_data,
                "unit": unit if outcome.data_status == "SUCCESS" else None,
                "currency": currency if outcome.data_status == "SUCCESS" else None,
            }
        )

    def _normalize_table_data(
        self,
        table_data: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if table_data is None:
            return None
        rows = table_data.get("rows", [])
        normalized_rows: list[list[str | None]] = []
        for row in rows:
            normalized_row: list[str | None] = []
            for cell in row:
                normalized_row.append(self._normalize_cell(cell))
            normalized_rows.append(normalized_row)
        return {
            "headers": table_data.get("headers", []),
            "rows": normalized_rows,
        }

    def _normalize_cell(self, cell: object) -> str | None:
        if cell is None:
            return None
        text = str(cell).strip()
        if text in {"", "-"}:
            return None
        if text in {"0", "0.0", "0.00"}:
            return "0.00"
        return text

    def _extract_unit_currency(
        self,
        *,
        decision: RouteDecision,
        content_blocks: list[ArtifactContentBlock],
    ) -> tuple[str | None, str | None]:
        texts = self._candidate_texts(decision=decision, content_blocks=content_blocks)
        for text in texts:
            for pattern, normalized in self._UNIT_PATTERNS:
                if pattern.search(text):
                    return normalized
        return None, None

    def _candidate_texts(
        self,
        *,
        decision: RouteDecision,
        content_blocks: list[ArtifactContentBlock],
    ) -> list[str]:
        page_numbers = set()
        if decision.matched_table is not None:
            page_numbers = {
                segment.page_idx for segment in decision.matched_table.segments
            }
        nearby_texts = [
            block.text.strip()
            for block in content_blocks
            if block.type == "text"
            and block.text
            and (not page_numbers or block.page_idx in page_numbers)
            and block.text.strip()
        ]
        return [*nearby_texts, *decision.context_blocks, *decision.matched_path]
```

- [ ] **Step 4: Run the normalization tests**

Run: `.venv/bin/python -m pytest tests/core_service/test_extraction_normalizer.py -q`

Expected: PASS with `2 passed`

- [ ] **Step 5: Commit the normalization layer**

```bash
git add apps/core_service/app/schemas/normalization.py apps/core_service/app/schemas/extraction.py apps/core_service/app/services/extraction_normalizer.py tests/core_service/test_extraction_normalizer.py
git commit -m "feat(normalize): 增加提取结果归一化"
```

## Task 2: Add Confidence Scorer And Task Status Evaluator

**Files:**
- Create: `apps/core_service/app/services/confidence_scorer.py`
- Create: `apps/core_service/app/services/task_status_evaluator.py`
- Create: `tests/core_service/test_confidence_scorer.py`

- [ ] **Step 1: Write the failing scoring and review gate tests**

```python
# tests/core_service/test_confidence_scorer.py
from decimal import Decimal

from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.services.confidence_scorer import ConfidenceScorer
from apps.core_service.app.services.task_status_evaluator import TaskStatusEvaluator
from apps.shared.enums.task_status import TaskStatus


def test_scorer_keeps_fast_track_success_with_unit_at_full_score() -> None:
    outcome = ExtractionOutcome(
        data_status="SUCCESS",
        extraction_route="FAST_TRACK",
        table_data={"headers": ["分部", "收入"], "rows": [["境内", "100"]]},
        confidence_score=Decimal("95.00"),
        needs_review="0",
        unit="CNY_TEN_THOUSAND",
        currency="CNY",
    )

    scored = ConfidenceScorer().apply(outcome=outcome)

    assert scored.confidence_score == Decimal("100.00")
    assert scored.needs_review == "0"


def test_scorer_flags_slow_track_success_without_unit_for_review() -> None:
    outcome = ExtractionOutcome(
        data_status="SUCCESS",
        extraction_route="SLOW_TRACK",
        table_data={"headers": ["分部", "收入"], "rows": [["主营业务", "100"]]},
        confidence_score=Decimal("88.00"),
        needs_review="0",
        unit=None,
        currency=None,
    )

    scored = ConfidenceScorer().apply(outcome=outcome)

    assert scored.confidence_score == Decimal("75.00")
    assert scored.needs_review == "1"


def test_scorer_keeps_not_disclosed_slow_track_at_review_threshold() -> None:
    outcome = ExtractionOutcome(
        data_status="NOT_DISCLOSED",
        extraction_route="SLOW_TRACK",
        table_data=None,
        confidence_score=Decimal("88.00"),
        needs_review="0",
    )

    scored = ConfidenceScorer().apply(outcome=outcome)

    assert scored.confidence_score == Decimal("85.00")
    assert scored.needs_review == "0"


def test_task_status_evaluator_returns_pending_review_when_any_result_needs_review() -> None:
    evaluator = TaskStatusEvaluator()
    status = evaluator.evaluate(
        outcomes=[
            ExtractionOutcome(
                data_status="SUCCESS",
                extraction_route="FAST_TRACK",
                table_data={"headers": [], "rows": []},
                confidence_score=Decimal("100.00"),
                needs_review="0",
            ),
            ExtractionOutcome(
                data_status="SUCCESS",
                extraction_route="SLOW_TRACK",
                table_data={"headers": [], "rows": []},
                confidence_score=Decimal("75.00"),
                needs_review="1",
            ),
        ]
    )

    assert status == TaskStatus.PENDING_REVIEW
```

- [ ] **Step 2: Run the scoring tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core_service/test_confidence_scorer.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.services.confidence_scorer'`

- [ ] **Step 3: Add the scorer and task status evaluator**

```python
# apps/core_service/app/services/confidence_scorer.py
from decimal import Decimal

from apps.core_service.app.schemas.extraction import ExtractionOutcome


class ConfidenceScorer:
    def apply(self, *, outcome: ExtractionOutcome) -> ExtractionOutcome:
        score = Decimal("100.00")
        if outcome.extraction_route == "SLOW_TRACK":
            score -= Decimal("15.00")
        if outcome.data_status == "SUCCESS" and outcome.unit is None:
            score -= Decimal("10.00")
        score = max(score, Decimal("0.00"))
        return outcome.model_copy(
            update={
                "confidence_score": score,
                "needs_review": "1" if score < Decimal("85.00") else "0",
            }
        )
```

```python
# apps/core_service/app/services/task_status_evaluator.py
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.shared.enums.task_status import TaskStatus


class TaskStatusEvaluator:
    def evaluate(self, *, outcomes: list[ExtractionOutcome]) -> TaskStatus:
        if any(outcome.needs_review == "1" for outcome in outcomes):
            return TaskStatus.PENDING_REVIEW
        return TaskStatus.COMPLETED
```

- [ ] **Step 4: Run the scoring tests**

Run: `.venv/bin/python -m pytest tests/core_service/test_confidence_scorer.py -q`

Expected: PASS with `4 passed`

- [ ] **Step 5: Commit the scoring and review gate**

```bash
git add apps/core_service/app/services/confidence_scorer.py apps/core_service/app/services/task_status_evaluator.py tests/core_service/test_confidence_scorer.py
git commit -m "feat(score): 增加置信度与复核门禁"
```

## Task 3: Wire Normalization And Scoring Into Extractor Worker

**Files:**
- Modify: `apps/core_service/app/services/extractor_worker.py`
- Modify: `tests/core_service/test_extractor_worker.py`

- [ ] **Step 1: Write the failing worker assertions for normalized metadata and review gating**

```python
# tests/core_service/test_extractor_worker.py
def build_multi_page_content_list() -> bytes:
    return json.dumps(
        [
            {
                "type": "text",
                "page_idx": 0,
                "bbox": [0.0, 0.0, 200.0, 20.0],
                "text": "主营业务收入",
            },
            {
                "type": "text",
                "page_idx": 0,
                "bbox": [0.0, 20.0, 200.0, 40.0],
                "text": "单位：人民币万元",
            },
            {
                "type": "table",
                "page_idx": 0,
                "bbox": [0.0, 40.0, 300.0, 180.0],
                "table_body": [["分部", "收入"], ["境内", "-"], ["境外", "0"]],
                "metadata": {
                    "section_path": ["管理层讨论与分析", "主营业务分析"],
                },
            },
            {
                "type": "text",
                "page_idx": 1,
                "bbox": [0.0, 0.0, 200.0, 20.0],
                "text": "续表：主营业务收入",
            },
            {
                "type": "table",
                "page_idx": 1,
                "bbox": [0.0, 40.0, 300.0, 140.0],
                "table_body": [["分部", "收入"], ["其他", "20"]],
                "metadata": {
                    "section_path": ["管理层讨论与分析", "主营业务分析"],
                },
            },
        ],
        ensure_ascii=True,
    ).encode("utf-8")


async def test_extractor_worker_persists_normalized_fast_track_results(
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

    parser_worker = build_parser_worker(test_app)
    assert await parser_worker.process_next_message(timeout_seconds=0) is True
    await test_app.state.object_storage_client.upload_bytes(
        bucket=bucket,
        object_key=content_key,
        data=build_multi_page_content_list(),
        content_type="application/json",
    )
    test_app.state.rule_repository.rules = [_rule()]

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    fetch_response = await async_client.get(f"/api/v1/tasks/{task_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == "COMPLETED"

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].task_id == task_id
    assert rows[0].rule_id == 3001
    assert rows[0].target_table_code == "main_business_revenue"
    assert rows[0].data_status == "SUCCESS"
    assert rows[0].extraction_route == "FAST_TRACK"
    assert rows[0].unit == "CNY_TEN_THOUSAND"
    assert rows[0].currency == "CNY"
    assert rows[0].table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", None], ["境外", "0.00"], ["其他", "20"]],
    }
    assert rows[0].confidence_score == Decimal("100.00")
    assert rows[0].needs_review == "0"


async def test_extractor_worker_marks_pending_review_for_low_confidence_slow_track_result(
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
        data=build_non_standard_section_content_list(),
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
    test_app.state.rule_repository.rules = [_rule()]
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

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == "PENDING_REVIEW"

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].data_status == "SUCCESS"
    assert rows[0].extraction_route == "SLOW_TRACK"
    assert rows[0].unit is None
    assert rows[0].currency is None
    assert rows[0].confidence_score == Decimal("75.00")
    assert rows[0].needs_review == "1"
    assert test_app.state.llm_fallback_client.calls[0]["target_table_code"] == (
        "main_business_revenue"
    )
```

- [ ] **Step 2: Run the worker suite to verify the new assertions fail**

Run: `.venv/bin/python -m pytest tests/core_service/test_extractor_worker.py -q`

Expected: FAIL because the current worker does not run normalization, scoring, or task-level review gating

- [ ] **Step 3: Integrate the post-processing pipeline into the worker**

```python
# apps/core_service/app/services/extractor_worker.py
from apps.core_service.app.services.confidence_scorer import ConfidenceScorer
from apps.core_service.app.services.extraction_normalizer import ExtractionNormalizer
from apps.core_service.app.services.task_status_evaluator import TaskStatusEvaluator


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
        extraction_normalizer: ExtractionNormalizer | None = None,
        confidence_scorer: ConfidenceScorer | None = None,
        task_status_evaluator: TaskStatusEvaluator | None = None,
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
        self._logical_table_builder = logical_table_builder or LogicalTableBuilder()
        self._table_router = table_router or TableRouter()
        self._fast_track_extractor = fast_track_extractor or FastTrackExtractor()
        self._llm_fallback_client = llm_fallback_client or DisabledLLMFallbackClient()
        self._extraction_normalizer = extraction_normalizer or ExtractionNormalizer()
        self._confidence_scorer = confidence_scorer or ConfidenceScorer()
        self._task_status_evaluator = task_status_evaluator or TaskStatusEvaluator()
```

在 `process_next_message()` 的第二个数据库事务里，用下面这段替换当前的 `for rule in rules` 循环和固定 `TaskStatus.COMPLETED` 写回逻辑：

```python
final_outcomes: list[ExtractionOutcome] = []
for rule in rules:
    decision = self._table_router.route(
        rule=rule,
        logical_tables=logical_tables,
        content_blocks=content_blocks,
    )
    raw_outcome = await self._build_outcome(rule=rule, decision=decision)
    normalized_outcome = self._extraction_normalizer.normalize(
        outcome=raw_outcome,
        decision=decision,
        content_blocks=content_blocks,
    )
    scored_outcome = self._confidence_scorer.apply(outcome=normalized_outcome)
    final_outcomes.append(scored_outcome)
    await self._result_repository.upsert_result(
        session,
        result_id=self._id_generator.next_id(),
        task_id=task.id,
        rule=rule,
        outcome=scored_outcome,
    )

await self._task_repository.set_status(
    session,
    task,
    status=self._task_status_evaluator.evaluate(outcomes=final_outcomes),
    remark=None if rules else "No active extraction rules configured.",
)
await session.commit()
```

- [ ] **Step 4: Run the worker and post-processing regression suites**

Run: `.venv/bin/python -m pytest tests/core_service/test_extractor_worker.py tests/core_service/test_extraction_normalizer.py tests/core_service/test_confidence_scorer.py -q`

Expected: PASS with `14 passed`

- [ ] **Step 5: Commit the integrated post-processing flow**

```bash
git add apps/core_service/app/services/extractor_worker.py tests/core_service/test_extractor_worker.py
git commit -m "feat(worker): 接入归一化与评分流程"
```

## Completion Verification

- [ ] **Step 1: Run the full repository test suite**

Run: `.venv/bin/python -m pytest tests -q`

Expected: PASS with `44 passed`

- [ ] **Step 2: Confirm the diff is limited to Phase 4/5 post-processing files**

Run: `git diff --stat HEAD~3..HEAD`

Expected: only the files listed in `File Structure`, with no migration, dependency, queue, or parser changes

## Self-Review

### Spec Coverage

- `0.00` / `null` / `"NOT_DISCLOSED"` / `"NOT_FIND"` 语义分层：Task 1 + Task 3
- 单位/币种提取与标准化：Task 1 + Task 3
- `confidence_score` 计算：Task 2 + Task 3
- `needs_review`：Task 2 + Task 3
- `COMPLETED | PENDING_REVIEW` 任务级状态：Task 2 + Task 3

### Intentional Deferrals

- 插件式后处理脚本：未纳入本计划，避免把策略注册、脚本执行和评分主链路耦合在一起。
- review queue / traceability / 前端复核：未纳入本计划，当前只做后端 review gate。
- 更广的单位/币种枚举：未纳入本计划，先收敛到当前需求和测试中最稳定的 `CNY` 场景。

### Placeholder Scan

- 本计划没有使用 `TODO`、`TBD`、`implement later` 或 “类似 Task N” 的占位描述。
- 每个 task 都给出了明确文件路径、测试代码、命令和预期结果。
- 类型和命名在全文保持一致：`ExtractionNormalizer`、`ConfidenceScorer`、`TaskStatusEvaluator`、`ExtractionOutcome`。
