# Real MinerU Parser Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用真实 MinerU 解析替换当前 skeleton parser，并继续输出 Core Service 现有可消费的 canonical `content_list.json`。

**Architecture:** 保持 `POST /api/v1/extract -> parser_queue -> parser_service -> extractor_queue` 主链路和对象存储路径不变。Parser Service 新增一个 CLI-backed `MinerUParserEngine`，把上传的 PDF 临时落盘、调用官方 `mineru -p <input> -o <output>` 命令生成原始产物，再用本仓库自定义 normalizer 收敛为当前 Core Service 已依赖的 canonical block contract。运行时通过 `parser_backend=skeleton|mineru` 控制解析后端，测试继续走 `skeleton` 或 stub runner。

**Tech Stack:** Python 3.13, FastAPI, asyncio, subprocess, tempfile, MinIO, pytest, MinerU CLI

---

## File Structure

- Create: `apps/parser_service/app/services/mineru_artifact_normalizer.py`
- Create: `apps/parser_service/app/services/mineru_parser_engine.py`
- Create: `apps/parser_service/app/services/parser_engine_factory.py`
- Modify: `apps/parser_service/app/services/parser_engine.py`
- Modify: `apps/parser_service/app/settings.py`
- Modify: `apps/parser_service/app/main.py`
- Create: `tests/fixtures/mineru/sample_content_list.json`
- Create: `tests/parser_service/test_mineru_artifact_normalizer.py`
- Create: `tests/parser_service/test_mineru_parser_engine.py`
- Modify: `tests/parser_service/test_worker.py`

## Preflight

- [ ] **Step 1: Verify the current parser baseline**

Run: `.venv/bin/python -m pytest tests/parser_service/test_worker.py -q`
Expected: PASS with `4 passed`

- [ ] **Step 2: Verify the canonical artifact baseline still holds before touching parser runtime**

Run: `.venv/bin/python -m pytest tests/core_service/test_artifact_loading.py tests/core_service/test_logical_table_builder.py -q`
Expected: PASS

### Task 1: Add A Canonical MinerU Artifact Normalizer

**Files:**
- Create: `tests/fixtures/mineru/sample_content_list.json`
- Create: `tests/parser_service/test_mineru_artifact_normalizer.py`
- Create: `apps/parser_service/app/services/mineru_artifact_normalizer.py`

- [ ] **Step 1: Write the failing fixture and normalizer test**

```json
[
  {
    "type": "text",
    "page_idx": 0,
    "bbox": [0.0, 0.0, 120.0, 20.0],
    "text": "管理层讨论与分析",
    "section_path": ["管理层讨论与分析"],
    "block_role": "heading",
    "span_count": 3
  },
  {
    "type": "text",
    "page_idx": 0,
    "bbox": [0.0, 24.0, 200.0, 44.0],
    "text": "主营业务分析",
    "section_path": ["管理层讨论与分析", "主营业务分析"],
    "block_role": "heading",
    "span_count": 2
  },
  {
    "type": "table",
    "page_idx": 0,
    "bbox": [0.0, 48.0, 300.0, 180.0],
    "table_body": [["分部", "营业收入"], ["境内", "100"]],
    "section_path": ["管理层讨论与分析", "主营业务分析"],
    "img_path": "tables/page-0-table-0.png"
  }
]
```

```python
import json
from pathlib import Path

from apps.parser_service.app.services.mineru_artifact_normalizer import (
    normalize_mineru_content_list,
)


def test_normalizer_converts_raw_mineru_blocks_to_canonical_contract() -> None:
    raw_blocks = json.loads(
        Path("tests/fixtures/mineru/sample_content_list.json").read_text(encoding="utf-8")
    )

    blocks = normalize_mineru_content_list(raw_blocks)

    assert blocks[0]["type"] == "text"
    assert blocks[0]["page_idx"] == 0
    assert blocks[0]["bbox"] == [0.0, 0.0, 120.0, 20.0]
    assert blocks[0]["text"] == "管理层讨论与分析"
    assert blocks[0]["metadata"]["section_path"] == ["管理层讨论与分析"]
    assert blocks[0]["metadata"]["block_role"] == "heading"
    assert blocks[0]["span_count"] == 3

    assert blocks[2]["type"] == "table"
    assert blocks[2]["table_body"] == [["分部", "营业收入"], ["境内", "100"]]
    assert blocks[2]["metadata"]["section_path"] == ["管理层讨论与分析", "主营业务分析"]
    assert blocks[2]["img_path"] == "tables/page-0-table-0.png"
```

- [ ] **Step 2: Run the new normalizer test to verify it fails**

Run: `.venv/bin/python -m pytest tests/parser_service/test_mineru_artifact_normalizer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.parser_service.app.services.mineru_artifact_normalizer'`

- [ ] **Step 3: Implement the canonical normalizer**

```python
from collections.abc import Sequence
from typing import Any


def normalize_mineru_content_list(raw_blocks: Sequence[dict[str, Any]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []

    for raw in raw_blocks:
        block_type = str(raw.get("type", "")).strip().lower()
        if block_type not in {"text", "table"}:
            continue

        item: dict[str, object] = {
            "type": block_type,
            "page_idx": int(raw.get("page_idx", 0)),
            "bbox": [float(value) for value in raw.get("bbox", [0.0, 0.0, 0.0, 0.0])],
            "metadata": _build_metadata(raw),
        }

        if block_type == "text":
            item["text"] = str(raw.get("text", "")).strip()
        else:
            item["table_body"] = _normalize_table_body(raw.get("table_body"))

        for key, value in raw.items():
            if key in {"type", "page_idx", "bbox", "text", "table_body", "section_path", "metadata"}:
                continue
            item[key] = value

        normalized.append(item)

    return normalized


def _build_metadata(raw: dict[str, Any]) -> dict[str, object]:
    metadata = dict(raw.get("metadata") or {})

    raw_path = raw.get("section_path", [])
    section_path = [str(item).strip() for item in raw_path if str(item).strip()]
    if section_path:
        metadata["section_path"] = section_path

    block_role = raw.get("block_role")
    if isinstance(block_role, str) and block_role.strip():
        metadata["block_role"] = block_role.strip()

    return metadata


def _normalize_table_body(value: object) -> list[list[str | None]]:
    if not isinstance(value, list):
        return []

    rows: list[list[str | None]] = []
    for row in value:
        if not isinstance(row, list):
            continue
        rows.append([None if cell is None else str(cell) for cell in row])
    return rows
```

- [ ] **Step 4: Run the normalizer suite**

Run: `.venv/bin/python -m pytest tests/parser_service/test_mineru_artifact_normalizer.py tests/core_service/test_artifact_loading.py -q`
Expected: PASS

- [ ] **Step 5: Commit the canonical normalizer**

```bash
git add tests/fixtures/mineru/sample_content_list.json tests/parser_service/test_mineru_artifact_normalizer.py apps/parser_service/app/services/mineru_artifact_normalizer.py
git commit -m "feat(parser): 新增 MinerU 产物归一化"
```

### Task 2: Add A CLI-Backed MinerU Parser Engine

**Files:**
- Create: `tests/parser_service/test_mineru_parser_engine.py`
- Create: `apps/parser_service/app/services/mineru_parser_engine.py`
- Modify: `apps/parser_service/app/services/parser_engine.py`

- [ ] **Step 1: Write the failing engine test**

```python
import json
from pathlib import Path

from apps.core_service.app.schemas.queue import ParserTaskMessage
from apps.parser_service.app.services.mineru_parser_engine import MinerUParserEngine


class StubRunner:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path
        self.calls: list[tuple[str, int, str]] = []

    def __call__(self, *, input_pdf_path: Path, output_dir: Path, timeout_seconds: int, backend: str | None) -> None:
        self.calls.append((input_pdf_path.name, timeout_seconds, backend or "auto"))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "content_list.json").write_text(
            self.fixture_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


async def test_mineru_parser_engine_invokes_runner_and_returns_canonical_payload(tmp_path) -> None:
    runner = StubRunner(Path("tests/fixtures/mineru/sample_content_list.json"))
    engine = MinerUParserEngine(
        temp_dir_root=tmp_path,
        timeout_seconds=45,
        backend="pipeline",
        command_runner=runner,
    )

    payload = await engine.parse(
        source_pdf=b"%PDF-1.7\nmineru",
        message=ParserTaskMessage(
            task_id="1001",
            doc_type="ANNUAL_REPORT",
            file_name="report.pdf",
            file_hash="abc",
            file_size=7,
            bucket="test-bucket",
            source_object_key="tasks/1001/source/report.pdf",
        ),
    )

    blocks = json.loads(payload)
    assert runner.calls == [("report.pdf", 45, "pipeline")]
    assert blocks[0]["metadata"]["block_role"] == "heading"
    assert blocks[2]["metadata"]["section_path"] == ["管理层讨论与分析", "主营业务分析"]
```

- [ ] **Step 2: Run the engine test to verify it fails**

Run: `.venv/bin/python -m pytest tests/parser_service/test_mineru_parser_engine.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.parser_service.app.services.mineru_parser_engine'`

- [ ] **Step 3: Implement the CLI-backed engine**

```python
import asyncio
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.core_service.app.schemas.queue import ParserTaskMessage
from apps.parser_service.app.services.mineru_artifact_normalizer import (
    normalize_mineru_content_list,
)
from apps.parser_service.app.services.parser_engine import ParserEngine, ParserEngineError

CommandRunner = Callable[[Path, Path, int, str | None], None]


class MinerUParserEngine(ParserEngine):
    def __init__(
        self,
        *,
        temp_dir_root: str | Path | None,
        timeout_seconds: int,
        backend: str | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._temp_dir_root = None if temp_dir_root is None else Path(temp_dir_root)
        self._timeout_seconds = timeout_seconds
        self._backend = backend
        self._command_runner = command_runner or _default_command_runner

    async def parse(self, *, source_pdf: bytes, message: ParserTaskMessage) -> bytes:
        if not source_pdf.startswith(b"%PDF"):
            raise ParserEngineError(
                "Source file does not look like a PDF document.",
                reason="InvalidPdfSignature",
            )

        with TemporaryDirectory(dir=self._temp_dir_root) as workdir:
            workdir_path = Path(workdir)
            input_pdf_path = workdir_path / message.file_name
            output_dir = workdir_path / "mineru-output"
            input_pdf_path.write_bytes(source_pdf)

            try:
                await asyncio.to_thread(
                    self._command_runner,
                    input_pdf_path=input_pdf_path,
                    output_dir=output_dir,
                    timeout_seconds=self._timeout_seconds,
                    backend=self._backend,
                )
                raw_blocks = json.loads((output_dir / "content_list.json").read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise ParserEngineError(
                    "MinerU output did not contain content_list.json.",
                    reason="ContentListMissing",
                ) from exc
            except (json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
                raise ParserEngineError(
                    "Failed to parse source PDF with MinerU.",
                    reason=exc.__class__.__name__,
                ) from exc

        canonical_blocks = normalize_mineru_content_list(raw_blocks)
        return json.dumps(canonical_blocks, ensure_ascii=True).encode("utf-8")


def _default_command_runner(
    *,
    input_pdf_path: Path,
    output_dir: Path,
    timeout_seconds: int,
    backend: str | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = ["mineru", "-p", str(input_pdf_path), "-o", str(output_dir)]
    if backend:
        command.extend(["-b", backend])
    subprocess.run(command, check=True, timeout=timeout_seconds, capture_output=True, text=True)
```

- [ ] **Step 4: Run the engine suite**

Run: `.venv/bin/python -m pytest tests/parser_service/test_mineru_parser_engine.py tests/parser_service/test_mineru_artifact_normalizer.py -q`
Expected: PASS

- [ ] **Step 5: Commit the CLI-backed engine**

```bash
git add tests/parser_service/test_mineru_parser_engine.py apps/parser_service/app/services/parser_engine.py apps/parser_service/app/services/mineru_parser_engine.py
git commit -m "feat(parser): 接入 MinerU CLI 解析引擎"
```

### Task 3: Wire Runtime Settings And Parser Service Construction

**Files:**
- Create: `apps/parser_service/app/services/parser_engine_factory.py`
- Modify: `apps/parser_service/app/settings.py`
- Modify: `apps/parser_service/app/main.py`
- Modify: `tests/parser_service/test_worker.py`

- [ ] **Step 1: Write the failing runtime wiring tests**

```python
from apps.parser_service.app.services.mineru_parser_engine import MinerUParserEngine
from apps.parser_service.app.services.parser_engine import SkeletonParserEngine
from apps.parser_service.app.services.parser_engine_factory import build_parser_engine
from apps.parser_service.app.settings import Settings


def test_build_parser_engine_returns_mineru_engine_when_backend_selected(tmp_path) -> None:
    settings = Settings(
        parser_backend="mineru",
        parser_timeout_seconds=60,
        parser_temp_dir=str(tmp_path),
        mineru_backend="pipeline",
    )

    engine = build_parser_engine(settings)

    assert isinstance(engine, MinerUParserEngine)


def test_build_parser_engine_returns_skeleton_for_local_contract_tests() -> None:
    settings = Settings(parser_backend="skeleton")

    engine = build_parser_engine(settings)

    assert isinstance(engine, SkeletonParserEngine)
```

```python
async def test_parser_worker_emits_canonical_artifact_from_mineru_engine(async_client, test_app, tmp_path) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("handoff.pdf", b"%PDF-1.7\nhandoff", "application/pdf")},
    )
    payload = response.json()

    runner = StubRunner(Path("tests/fixtures/mineru/sample_content_list.json"))
    worker = build_worker(
        test_app,
        MinerUParserEngine(
            temp_dir_root=tmp_path,
            timeout_seconds=30,
            backend="pipeline",
            command_runner=runner,
        ),
    )

    assert await worker.process_next_message(timeout_seconds=0) is True
    artifact_key = build_content_list_object_key(int(payload["task_id"]))
    artifact_upload = next(
        upload for upload in test_app.state.object_storage_client.uploads if upload.object_key == artifact_key
    )
    assert json.loads(artifact_upload.data.decode("utf-8"))[2]["metadata"]["section_path"] == [
        "管理层讨论与分析",
        "主营业务分析",
    ]
```

- [ ] **Step 2: Run the wiring tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/parser_service/test_mineru_parser_engine.py tests/parser_service/test_worker.py -q`
Expected: FAIL because `build_parser_engine` and the new settings fields do not exist

- [ ] **Step 3: Implement runtime settings and engine construction**

```python
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "financial-table-extractor-parser-service"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:25432/financial_table_extractor"
    redis_url: str = "redis://localhost:26379/0"
    parser_queue_name: str = "parser_queue"
    extractor_queue_name: str = "extractor_queue"
    minio_endpoint: str = "http://localhost:29000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "financial-table-extractor"
    log_level: str = "INFO"
    parser_poll_timeout_seconds: int = Field(default=5, ge=0, le=300)
    parser_backend: Literal["skeleton", "mineru"] = "skeleton"
    parser_timeout_seconds: int = Field(default=180, ge=1, le=3600)
    parser_temp_dir: str | None = None
    mineru_backend: Literal["pipeline"] | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

```python
from apps.parser_service.app.services.mineru_parser_engine import MinerUParserEngine
from apps.parser_service.app.services.parser_engine import SkeletonParserEngine


def build_parser_engine(settings):
    if settings.parser_backend == "mineru":
        return MinerUParserEngine(
            temp_dir_root=settings.parser_temp_dir,
            timeout_seconds=settings.parser_timeout_seconds,
            backend=settings.mineru_backend,
        )
    return SkeletonParserEngine()
```

```python
from apps.parser_service.app.services.parser_engine_factory import build_parser_engine


async def run(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    parser_engine = build_parser_engine(app_settings)
    worker = ParserWorker(
        session_factory=database_client.session_factory,
        object_storage_client=object_storage_client,
        queue_client=queue_client,
        parser_engine=parser_engine,
        logger=logger,
    )
```

- [ ] **Step 4: Run the parser service regression suite**

Run: `.venv/bin/python -m pytest tests/parser_service/test_worker.py tests/parser_service/test_mineru_artifact_normalizer.py tests/parser_service/test_mineru_parser_engine.py -q`
Expected: PASS

- [ ] **Step 5: Commit the parser runtime wiring**

```bash
git add apps/parser_service/app/services/parser_engine_factory.py apps/parser_service/app/settings.py apps/parser_service/app/main.py tests/parser_service/test_worker.py
git commit -m "feat(parser): 切换可配置解析后端"
```

## Final Verification

- [ ] **Step 1: Run the parser-focused suite**

Run: `.venv/bin/python -m pytest tests/parser_service tests/core_service/test_artifact_loading.py tests/core_service/test_logical_table_builder.py -q`
Expected: PASS

- [ ] **Step 2: Run the full repository suite**

Run: `.venv/bin/python -m pytest tests -q`
Expected: PASS

## Assumptions

- GPU/生产环境将通过 `PARSER_BACKEND=mineru` 启用真实解析；本地开发和单测默认继续使用 `skeleton`。
- CLI 调用遵循 MinerU 官方 README 当前公开的命令格式：`mineru -p <input_path> -o <output_path>`，纯 CPU 环境追加 `-b pipeline`。来源：官方仓库 README `https://github.com/opendatalab/MinerU`
- canonical artifact 继续以当前 Core Service 契约为准：`type/page_idx/bbox` 必填，文本块提供 `text`，表格块提供 `table_body`，有用的章节信息进入 `metadata.section_path`，其余 MinerU 字段原样透传。
