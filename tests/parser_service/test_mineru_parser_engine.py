import json
from pathlib import Path

import pytest

from apps.core_service.app.schemas.queue import ParserTaskMessage
from apps.parser_service.app.services.mineru_parser_engine import MinerUParserEngine
from apps.parser_service.app.services.parser_engine import ParserEngineError, SkeletonParserEngine
from apps.parser_service.app.services.parser_engine_factory import build_parser_engine
from apps.parser_service.app.settings import Settings


class StubRunner:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path
        self.calls: list[tuple[str, int, str]] = []

    def __call__(
        self,
        *,
        input_pdf_path: Path,
        output_dir: Path,
        timeout_seconds: int,
        backend: str | None,
    ) -> None:
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


async def test_mineru_parser_engine_maps_tempdir_oserror_to_parser_engine_error(tmp_path) -> None:
    invalid_temp_root = tmp_path / "occupied-path"
    invalid_temp_root.write_text("not-a-directory", encoding="utf-8")
    engine = MinerUParserEngine(
        temp_dir_root=invalid_temp_root,
        timeout_seconds=45,
    )

    with pytest.raises(ParserEngineError) as exc_info:
        await engine.parse(
            source_pdf=b"%PDF-1.7\nmineru",
            message=ParserTaskMessage(
                task_id="1002",
                doc_type="ANNUAL_REPORT",
                file_name="report.pdf",
                file_hash="def",
                file_size=7,
                bucket="test-bucket",
                source_object_key="tasks/1002/source/report.pdf",
            ),
        )

    assert exc_info.value.reason == "NotADirectoryError"


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
