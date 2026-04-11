# Pagination Merge And Logical Table Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 extractor 在消费 `content_list.json` 后的第一步从“只校验 JSON”升级为“构建可复用的 `LogicalTable` 列表”：识别跨页续表、剔除重复表头，并把逻辑表工件落到 MinIO 供后续语义路由复用。

**Architecture:** 保持 `parser_service -> extractor_queue -> core extractor worker` 主链路不变，不改 parser queue 契约、不引入语义匹配与表级提取。Core Service 复用已经落地的 canonical artifact schema，并新增 `LogicalTableBuilder` 把 MinerU 风格扁平 `content_list.json` 规范化为内存态 `LogicalTable[]`，再由 extractor worker 额外上传一个派生工件 `logical_tables.json`，最后继续沿用当前占位 `NOT_FIND` 结果写入流程。

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI, SQLAlchemy 2.x, MinIO, pytest

---

## Requirement And Design Comparison

已对齐的部分：

- `requirement.md` 与 `design.md` 都把 Phase 2 定义为：从 `content_list.json` 中识别相邻页连续表格，做纵向拼接，并剔除续页重复表头。
- 当前仓库已经具备 Phase 2 的触发入口：parser 会写 `tasks/{task_id}/content_list.json`，extractor worker 会消费该 artifact。
- 当前仓库已经具备测试友好的依赖注入基础：`tests/conftest.py` 里的 fake object storage 会记录所有上传工件，适合断言派生产物。

当前缺口：

- `apps/core_service/app/services/extractor_worker.py` 只做了 `json.loads(...)` 校验，没有真正消费 canonical schema，也没有接入表格块识别、跨页合并和 `logical_tables.json` 上传。
- `apps/core_service/app/services/logical_table_builder.py` 与 `tests/core_service/test_logical_table_builder.py` 还不存在，Phase 2 的核心合并策略还没落地。
- `apps/core_service/app/utils/object_storage.py` 目前只有 `source` 与 `content_list` 的对象键 helper，没有逻辑表派生产物路径。
- `requirement.md` 里提到的“前页底部无闭合线段”启发式目前无法实现，因为现有 placeholder artifact 与当前 canonical contract 都没有暴露线段几何元数据；这一版先只实现可验证的“续表文本提示”与“相邻页同 section_path + 同表头”规则。

本计划的设计决策：

- 为了让 Phase 2 能够独立测试、回放、调试，本计划在“内存态 `LogicalTable[]`”之外，额外把派生结果上传为 `tasks/{task_id}/logical_tables.json`。
- 不改数据库 schema，不新增 `t_document_toc`、`semantic_vector` 或任何路由表；这些属于下一份语义路由计划。
- 不修改 parser skeleton 输出；Phase 2 的测试直接手写 MinerU 风格 artifact 样例，避免把真实 MinerU 接入和分页合并绑在一起。
- `apps/core_service/app/schemas/artifact.py`、`apps/core_service/app/schemas/logical_table.py` 与 `tests/core_service/test_artifact_loading.py` 已经在当前仓库落地并通过测试，本计划从这个基线继续，不重复规划已完成工作。

## Scope Check

`requirement.md` 的 Phase 2 到 Phase 6 是连续链路，但当前最合理的拆分仍然是先只做 `Pagination Merge And Logical Table Builder`。本计划只覆盖：

1. 复用已落地的 `content_list.json` canonical schema
2. 相邻页同表识别与重复表头剔除
3. `LogicalTable[]` 派生产物落盘到 MinIO
4. extractor worker 接入这一层能力

本计划明确不做：

- 路径指纹粗排
- 锚点规则精排
- LLM fallback
- 单位/币种归一化
- 置信度评分
- 前端溯源接口

## File Structure

本计划基于当前仓库已存在的 schema 基线继续推进。相关文件分成“只读基线”和“本次改动”两组：

- Reference only: `apps/core_service/app/schemas/artifact.py`
  已定义 canonical `content_list` block schema 和 `load_content_list(...)`。
- Reference only: `apps/core_service/app/schemas/logical_table.py`
  已定义 `LogicalTable` 与 `LogicalTableSegment` 中间表示。
- Reference only: `tests/core_service/test_artifact_loading.py`
  已覆盖 canonical artifact 加载与非法 payload 校验，作为 Phase 2 的回归基线。
- Create: `apps/core_service/app/services/logical_table_builder.py`
  实现跨页续表识别、重复表头剔除和 `LogicalTable[]` 构建。
- Modify: `apps/core_service/app/utils/object_storage.py`
  增加 `build_logical_tables_object_key(task_id)`。
- Modify: `apps/core_service/app/services/extractor_worker.py`
  用 canonical loader + builder 替换裸 `json.loads(...)`，并上传 `logical_tables.json`。
- Create: `tests/core_service/test_logical_table_builder.py`
  覆盖分页合并、重复表头剔除、同路径续页合并与不应合并场景。
- Modify: `tests/core_service/test_extractor_worker.py`
  覆盖 extractor worker 上传 `logical_tables.json` 派生产物。

## Preflight

本计划不是从零开始，而是延续当前已提交基线。开始 Task 1 之前先确认下面两个基线：

- [ ] **Step 1: Verify the canonical artifact contract baseline**

Run: `.venv/bin/pytest tests/core_service/test_artifact_loading.py -q`

Expected: PASS with `2 passed`

- [ ] **Step 2: Verify the repository baseline before Phase 2 work**

Run: `.venv/bin/pytest -q`

Expected: PASS with `15 passed`

## Task 1: Implement Pagination Merge And Logical Table Builder

**Files:**
- Create: `apps/core_service/app/services/logical_table_builder.py`
- Create: `tests/core_service/test_logical_table_builder.py`

- [ ] **Step 1: Write the failing logical table builder tests**

```python
# tests/core_service/test_logical_table_builder.py
from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.services.logical_table_builder import LogicalTableBuilder


def _table_block(
    *,
    page_idx: int,
    bbox: list[float],
    rows: list[list[str]],
    section_path: list[str],
) -> ArtifactContentBlock:
    return ArtifactContentBlock(
        type="table",
        page_idx=page_idx,
        bbox=bbox,
        table_body=rows,
        metadata={"section_path": section_path},
    )


def _text_block(*, page_idx: int, text: str) -> ArtifactContentBlock:
    return ArtifactContentBlock(
        type="text",
        page_idx=page_idx,
        bbox=[0.0, 0.0, 200.0, 20.0],
        text=text,
    )


def test_builder_merges_adjacent_pages_and_drops_repeated_headers() -> None:
    blocks = [
        _text_block(page_idx=0, text="主营业务收入"),
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 180.0],
            rows=[["分部", "收入"], ["境内", "100"], ["境外", "80"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
        _text_block(page_idx=1, text="续表：主营业务收入"),
        _table_block(
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 140.0],
            rows=[["分部", "收入"], ["其他", "20"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 1
    assert tables[0].start_page == 0
    assert tables[0].end_page == 1
    assert tables[0].header == ["分部", "收入"]
    assert tables[0].rows == [["境内", "100"], ["境外", "80"], ["其他", "20"]]
    assert [segment.page_idx for segment in tables[0].segments] == [0, 1]
    assert tables[0].context_before == ["主营业务收入"]


def test_builder_merges_adjacent_pages_when_header_and_section_match() -> None:
    blocks = [
        _text_block(page_idx=0, text="主营业务收入"),
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 180.0],
            rows=[["分部", "收入"], ["境内", "100"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
        _table_block(
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 140.0],
            rows=[["分部", "收入"], ["境外", "80"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 1
    assert tables[0].rows == [["境内", "100"], ["境外", "80"]]
    assert [segment.page_idx for segment in tables[0].segments] == [0, 1]


def test_builder_keeps_distinct_tables_separate_when_section_changes() -> None:
    blocks = [
        _text_block(page_idx=0, text="按地区分类"),
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 160.0],
            rows=[["分部", "收入"], ["境内", "100"]],
            section_path=["管理层讨论与分析", "地区结构"],
        ),
        _text_block(page_idx=1, text="按产品分类"),
        _table_block(
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 160.0],
            rows=[["分部", "收入"], ["产品A", "100"]],
            section_path=["管理层讨论与分析", "产品结构"],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 2
    assert tables[0].rows == [["境内", "100"]]
    assert tables[1].rows == [["产品A", "100"]]
```

- [ ] **Step 2: Run the logical table builder tests to verify they fail**

Run: `.venv/bin/pytest tests/core_service/test_logical_table_builder.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.core_service.app.services.logical_table_builder'`

- [ ] **Step 3: Implement the logical table builder**

```python
# apps/core_service/app/services/logical_table_builder.py
from apps.core_service.app.schemas.artifact import ArtifactContentBlock, CellValue
from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment


class LogicalTableBuilder:
    def build(self, blocks: list[ArtifactContentBlock]) -> list[LogicalTable]:
        logical_tables: list[LogicalTable] = []
        active_table: LogicalTable | None = None
        active_header: list[str] | None = None
        active_block: ArtifactContentBlock | None = None

        for index, block in enumerate(blocks):
            if block.type != "table" or not block.table_body:
                continue

            header = self._normalize_row(block.table_body[0])
            rows = self._normalize_rows(block.table_body[1:])
            if active_table is None:
                active_table = self._new_logical_table(blocks, index, block, header, rows)
                active_header = header
                active_block = block
                continue

            if (
                active_header is not None
                and active_block is not None
                and self._should_merge(
                    previous_block=active_block,
                    next_block=block,
                    previous_header=active_header,
                    next_index=index,
                    blocks=blocks,
                )
            ):
                active_table.end_page = block.page_idx
                active_table.segments.append(
                    LogicalTableSegment(
                        page_idx=block.page_idx,
                        block_index=index,
                        bbox=block.bbox,
                    )
                )
                active_table.rows.extend(
                    self._normalize_rows(self._drop_repeated_header(block.table_body, active_header))
                )
                active_block = block
                continue

            logical_tables.append(active_table)
            active_table = self._new_logical_table(blocks, index, block, header, rows)
            active_header = header
            active_block = block

        if active_table is not None:
            logical_tables.append(active_table)

        return logical_tables

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
            segments=[
                LogicalTableSegment(
                    page_idx=block.page_idx,
                    block_index=index,
                    bbox=block.bbox,
                )
            ],
            context_before=self._collect_preceding_texts(blocks, index),
        )

    def _should_merge(
        self,
        *,
        previous_block: ArtifactContentBlock,
        next_block: ArtifactContentBlock,
        previous_header: list[str],
        next_index: int,
        blocks: list[ArtifactContentBlock],
    ) -> bool:
        if next_block.page_idx != previous_block.page_idx + 1:
            return False
        if self._normalize_row(next_block.table_body[0]) != previous_header:
            return False

        if any("续表" in text for text in self._collect_preceding_texts(blocks, next_index)):
            return True

        return self._section_path(previous_block) == self._section_path(next_block)

    def _collect_preceding_texts(
        self,
        blocks: list[ArtifactContentBlock],
        index: int,
        *,
        limit: int = 2,
    ) -> list[str]:
        texts: list[str] = []
        cursor = index - 1
        while cursor >= 0 and len(texts) < limit:
            block = blocks[cursor]
            cursor -= 1
            if block.type != "text" or block.text is None:
                continue
            normalized = block.text.strip()
            if normalized:
                texts.append(normalized)
        texts.reverse()
        return texts

    def _drop_repeated_header(
        self,
        rows: list[list[CellValue]],
        previous_header: list[str],
    ) -> list[list[CellValue]]:
        if rows and self._normalize_row(rows[0]) == previous_header:
            return rows[1:]
        return rows

    def _normalize_rows(self, rows: list[list[CellValue]]) -> list[list[str | None]]:
        normalized_rows: list[list[str | None]] = []
        for row in rows:
            normalized = self._normalize_row(row)
            if any(cell not in (None, "") for cell in normalized):
                normalized_rows.append(normalized)
        return normalized_rows

    def _normalize_row(self, row: list[CellValue]) -> list[str | None]:
        normalized: list[str | None] = []
        for cell in row:
            if cell is None:
                normalized.append(None)
                continue
            text = str(cell).replace("\n", " ").strip()
            normalized.append(text)
        return normalized

    def _section_path(self, block: ArtifactContentBlock) -> tuple[str, ...] | None:
        value = block.metadata.get("section_path")
        if not isinstance(value, list):
            return None
        if not all(isinstance(item, str) for item in value):
            return None
        return tuple(value)
```

- [ ] **Step 4: Run the baseline schema and new builder tests to verify they pass**

Run: `.venv/bin/pytest tests/core_service/test_artifact_loading.py tests/core_service/test_logical_table_builder.py -q`

Expected: PASS with `5 passed`

- [ ] **Step 5: Commit the pagination merge slice**

```bash
git add apps/core_service/app/services/logical_table_builder.py \
  tests/core_service/test_logical_table_builder.py
git commit -m "feat(extractor): 增加跨页逻辑表构建器"
```

## Task 2: Wire Logical Table Builder Into Extractor Worker

**Files:**
- Modify: `apps/core_service/app/utils/object_storage.py`
- Modify: `apps/core_service/app/services/extractor_worker.py`
- Modify: `tests/core_service/test_extractor_worker.py`

- [ ] **Step 1: Write the failing extractor worker integration test**

```python
# tests/core_service/test_extractor_worker.py
import json
from decimal import Decimal

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.queue import ExtractorTaskMessage
from apps.core_service.app.services.extractor_worker import ExtractorWorker
from apps.core_service.app.utils.object_storage import (
    build_content_list_object_key,
    build_logical_tables_object_key,
)
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
                "type": "table",
                "page_idx": 0,
                "bbox": [0.0, 40.0, 300.0, 180.0],
                "table_body": [["分部", "收入"], ["境内", "100"], ["境外", "80"]],
                "metadata": {
                    "section_path": ["管理层讨论与分析", "主营业务分析"]
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
                    "section_path": ["管理层讨论与分析", "主营业务分析"]
                },
            },
        ],
        ensure_ascii=True,
    ).encode("utf-8")


async def test_extractor_worker_uploads_logical_tables_artifact(async_client, test_app) -> None:
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
        data=build_multi_page_content_list(),
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
            semantic_anchor_text="主营业务收入 管理层讨论与分析 主营业务分析",
            min_match_score=Decimal("0.900"),
            is_active="1",
        )
    ]

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    logical_tables_upload = next(
        upload
        for upload in test_app.state.object_storage_client.uploads
        if upload.object_key == build_logical_tables_object_key(task_id)
    )
    logical_tables = json.loads(logical_tables_upload.data.decode("utf-8"))

    assert len(logical_tables) == 1
    assert logical_tables[0]["start_page"] == 0
    assert logical_tables[0]["end_page"] == 1
    assert logical_tables[0]["header"] == ["分部", "收入"]
    assert logical_tables[0]["rows"] == [["境内", "100"], ["境外", "80"], ["其他", "20"]]
```

- [ ] **Step 2: Run the extractor worker integration test to verify it fails**

Run: `.venv/bin/pytest tests/core_service/test_extractor_worker.py::test_extractor_worker_uploads_logical_tables_artifact -q`

Expected: FAIL with `ImportError` because `build_logical_tables_object_key` does not exist yet, or with `StopIteration` because extractor worker never uploads `logical_tables.json`

- [ ] **Step 3: Implement logical table artifact persistence in extractor worker**

```python
# apps/core_service/app/utils/object_storage.py
def build_source_object_key(task_id: int, file_name: str) -> str:
    sanitized_file_name = file_name.replace("\\", "/").split("/")[-1].strip()
    if not sanitized_file_name:
        sanitized_file_name = "upload.bin"
    return f"tasks/{task_id}/source/{sanitized_file_name}"


def build_content_list_object_key(task_id: int) -> str:
    return f"tasks/{task_id}/content_list.json"


def build_logical_tables_object_key(task_id: int) -> str:
    return f"tasks/{task_id}/logical_tables.json"
```

```python
# apps/core_service/app/services/extractor_worker.py
import json
import logging
from collections.abc import Callable
from uuid import uuid4

from pydantic import ValidationError
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
from apps.core_service.app.schemas.artifact import load_content_list
from apps.core_service.app.services.logical_table_builder import LogicalTableBuilder
from apps.core_service.app.utils.object_storage import build_logical_tables_object_key
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
        logical_table_builder: LogicalTableBuilder | None = None,
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
            content_blocks = load_content_list(artifact_bytes)
        except StorageClientError as exc:
            await self._mark_failed(
                int(message.task_id),
                remark="Failed to load parser artifact from object storage.",
                trace_id=trace_id,
                code="OBJECT_STORAGE_UNAVAILABLE",
                reason=exc.reason,
            )
            return True
        except ValidationError as exc:
            await self._mark_failed(
                int(message.task_id),
                remark="Parser artifact does not match the canonical content_list contract.",
                trace_id=trace_id,
                code="ARTIFACT_INVALID",
                reason=exc.__class__.__name__,
            )
            return True

        logical_tables = self._logical_table_builder.build(content_blocks)
        logical_tables_key = build_logical_tables_object_key(int(message.task_id))
        try:
            await self._object_storage_client.upload_bytes(
                bucket=message.bucket,
                object_key=logical_tables_key,
                data=json.dumps(
                    [table.model_dump(mode="json") for table in logical_tables],
                    ensure_ascii=True,
                ).encode("utf-8"),
                content_type="application/json",
            )
        except StorageClientError as exc:
            await self._mark_failed(
                int(message.task_id),
                remark="Failed to persist logical table artifact to object storage.",
                trace_id=trace_id,
                code="OBJECT_STORAGE_UNAVAILABLE",
                reason=exc.reason,
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
                "logical_tables_object_key": logical_tables_key,
                "logical_table_count": len(logical_tables),
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

- [ ] **Step 4: Run the targeted tests**

Run: `.venv/bin/pytest tests/core_service/test_artifact_loading.py tests/core_service/test_logical_table_builder.py tests/core_service/test_extractor_worker.py -q`

Expected: PASS with `7 passed`

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/pytest -q`

Expected: PASS with `19 passed`

- [ ] **Step 6: Commit the extractor integration slice**

```bash
git add apps/core_service/app/utils/object_storage.py \
  apps/core_service/app/services/extractor_worker.py \
  tests/core_service/test_extractor_worker.py
git commit -m "feat(extractor): 接入逻辑表分页合并产物"
```

## Self-Review

Spec coverage 检查：

- Phase 2 的核心输入输出已经覆盖：从 `content_list.json` 读入、构建 `LogicalTable[]`、相邻页合并、续页重复表头剔除。
- “续表” 文本提示和“同 section_path + 同表头”的连续性识别都在 builder 里落了代码与测试。
- `requirement.md` 里的“前页底部无闭合线段”启发式被显式标记为后续能力，不在这份计划中伪造实现；当前 canonical contract 已保留 `extra_fields` 扩展位，等真实 MinerU 线段元数据接入后再补独立计划。
- 本计划没有把路径指纹粗排、锚点精排、LLM fallback、单位归一化和置信度评分混进来，符合上一份计划的 follow-up 拆分顺序。

Placeholder 扫描：

- 本文没有使用 `TODO`、`TBD`、“类似上一任务” 或省略实现细节的描述。
- 每个代码步骤都给了具体文件路径、具体测试、具体命令和具体 commit 文案。

Type consistency 检查：

- canonical loader 统一暴露 `ArtifactContentBlock`
- builder 统一输出 `LogicalTable`
- worker 统一消费 `load_content_list(...)` 和 `LogicalTableBuilder.build(...)`
- 派生产物对象键统一为 `build_logical_tables_object_key(task_id)`
