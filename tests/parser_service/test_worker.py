import asyncio
import json
from pathlib import Path

from apps.core_service.app.utils.object_storage import build_content_list_object_key
from apps.parser_service.app.services.parser_engine import ParserEngine, SkeletonParserEngine
from apps.parser_service.app.services.mineru_parser_engine import MinerUParserEngine
from apps.parser_service.app.services.parser_worker import ParserWorker


class BlockingParserEngine(ParserEngine):
    def __init__(self, result_bytes: bytes) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._result_bytes = result_bytes

    async def parse(self, *, source_pdf: bytes, message) -> bytes:
        del source_pdf, message
        self.started.set()
        await self.release.wait()
        return self._result_bytes


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


def build_worker(test_app, parser_engine: ParserEngine) -> ParserWorker:
    return ParserWorker(
        session_factory=test_app.state.database_client.session_factory,
        object_storage_client=test_app.state.object_storage_client,
        queue_client=test_app.state.queue_client,
        parser_engine=parser_engine,
        logger=test_app.state.logger,
        repository=test_app.state.task_repository,
    )


async def test_parser_worker_marks_task_parsing_then_parsed(async_client, test_app) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("worker.pdf", b"%PDF-1.7\nworker", "application/pdf")},
    )
    payload = response.json()
    task_id = payload["task_id"]

    engine = BlockingParserEngine(
        b'[{"type":"text","page_idx":0,"bbox":[0,0,0,0],"text":"parsed"}]'
    )
    worker = build_worker(test_app, engine)

    run_task = asyncio.create_task(worker.process_next_message(timeout_seconds=0))
    await asyncio.wait_for(engine.started.wait(), timeout=1)

    parsing_response = await async_client.get(f"/api/v1/tasks/{task_id}")
    assert parsing_response.status_code == 200
    assert parsing_response.json()["status"] == "PARSING"

    engine.release.set()
    assert await run_task is True

    parsed_response = await async_client.get(f"/api/v1/tasks/{task_id}")
    assert parsed_response.status_code == 200
    assert parsed_response.json()["status"] == "PARSED"
    assert parsed_response.json()["remark"] is None

    artifact_key = build_content_list_object_key(int(task_id))
    artifact_upload = next(
        upload
        for upload in test_app.state.object_storage_client.uploads
        if upload.object_key == artifact_key
    )
    assert json.loads(artifact_upload.data.decode("utf-8"))[0]["text"] == "parsed"


async def test_parser_worker_emits_extractor_message(async_client, test_app) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "ANNUAL_REPORT"},
        files={"file": ("handoff.pdf", b"%PDF-1.7\nhandoff", "application/pdf")},
    )
    payload = response.json()

    worker = build_worker(test_app, SkeletonParserEngine())
    assert await worker.process_next_message(timeout_seconds=0) is True

    assert len(test_app.state.queue_client.extractor_messages) == 1
    message = test_app.state.queue_client.extractor_messages[0]
    assert message.task_id == payload["task_id"]
    assert message.doc_type == "ANNUAL_REPORT"
    assert message.bucket == test_app.state.object_storage_client.bucket_name
    assert message.content_list_object_key == build_content_list_object_key(int(payload["task_id"]))


async def test_parser_worker_marks_task_failed_on_parse_error(async_client, test_app) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "IPO_PROSPECTUS"},
        files={"file": ("invalid.pdf", b"not-a-pdf", "application/pdf")},
    )
    payload = response.json()

    worker = build_worker(test_app, SkeletonParserEngine())
    assert await worker.process_next_message(timeout_seconds=0) is True

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == "FAILED"
    assert fetch_response.json()["remark"] == "Failed to parse source PDF."


async def test_parser_worker_marks_task_failed_on_storage_error(async_client, test_app) -> None:
    response = await async_client.post(
        "/api/v1/extract",
        data={"doc_type": "BOND_REPORT"},
        files={"file": ("storage.pdf", b"%PDF-1.7\nstorage", "application/pdf")},
    )
    payload = response.json()
    test_app.state.object_storage_client.download_failures_remaining = 1

    worker = build_worker(test_app, SkeletonParserEngine())
    assert await worker.process_next_message(timeout_seconds=0) is True

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == "FAILED"
    assert fetch_response.json()["remark"] == "Failed to load source PDF from object storage."


async def test_parser_worker_emits_canonical_artifact_from_mineru_engine(
    async_client,
    test_app,
    tmp_path,
) -> None:
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
        upload
        for upload in test_app.state.object_storage_client.uploads
        if upload.object_key == artifact_key
    )
    assert json.loads(artifact_upload.data.decode("utf-8"))[2]["metadata"]["section_path"] == [
        "管理层讨论与分析",
        "主营业务分析",
    ]
