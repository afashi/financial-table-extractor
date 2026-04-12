import json
from decimal import Decimal

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.extraction import ExtractionOutcome
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
        llm_fallback_client=test_app.state.llm_fallback_client,
    )


def _rule(*, min_match_score: str = "0.850") -> TableExtractionRule:
    return TableExtractionRule(
        id=3001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule={
            "logic_match": {
                "required_headers": ["分部", "收入"],
                "required_context_keywords": ["主营业务收入"],
            }
        },
        semantic_anchor_text="主营业务收入 管理层讨论与分析 主营业务分析",
        min_match_score=Decimal(min_match_score),
        is_active="1",
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


def build_non_standard_section_content_list() -> bytes:
    return json.dumps(
        [
            {
                "type": "text",
                "page_idx": 0,
                "bbox": [0.0, 0.0, 200.0, 20.0],
                "text": "主营业务分析",
            },
            {
                "type": "text",
                "page_idx": 0,
                "bbox": [0.0, 20.0, 200.0, 40.0],
                "text": "公司主营业务收入如下。",
            },
            {
                "type": "table",
                "page_idx": 0,
                "bbox": [0.0, 40.0, 300.0, 140.0],
                "table_body": [["项目", "金额"], ["主营业务", "100"]],
                "metadata": {
                    "section_path": ["管理层讨论与分析", "主营业务分析"],
                },
            },
        ],
        ensure_ascii=True,
    ).encode("utf-8")


def build_missing_section_content_list() -> bytes:
    return json.dumps(
        [
            {
                "type": "text",
                "page_idx": 0,
                "bbox": [0.0, 0.0, 200.0, 20.0],
                "text": "公司治理",
            }
        ],
        ensure_ascii=True,
    ).encode("utf-8")


async def test_extractor_worker_persists_fast_track_results(async_client, test_app) -> None:
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

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].task_id == task_id
    assert rows[0].rule_id == 3001
    assert rows[0].target_table_code == "main_business_revenue"
    assert rows[0].data_status == "SUCCESS"
    assert rows[0].extraction_route == "FAST_TRACK"
    assert rows[0].table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", "100"], ["境外", "80"], ["其他", "20"]],
    }
    assert rows[0].confidence_score == Decimal("95.00")


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

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].data_status == "SUCCESS"
    assert rows[0].extraction_route == "SLOW_TRACK"
    assert rows[0].table_data == {
        "headers": ["分部", "收入"],
        "rows": [["主营业务", "100"]],
    }
    assert test_app.state.llm_fallback_client.calls[0]["target_table_code"] == (
        "main_business_revenue"
    )


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
        data=build_missing_section_content_list(),
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

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    rows = test_app.state.result_repository.rows
    assert len(rows) == 1
    assert rows[0].data_status == "NOT_FIND"
    assert rows[0].extraction_route is None
    assert rows[0].remark == "Section fingerprint was not found in the parsed artifact."


async def test_extractor_worker_uploads_logical_tables_artifact(
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
    test_app.state.rule_repository.rules = [_rule()]

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
    assert logical_tables[0]["section_path"] == ["管理层讨论与分析", "主营业务分析"]


async def test_extractor_worker_marks_failed_for_invalid_content_list_contract(
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
        data=b'{"type":"table","page_idx":0,"bbox":[0,0,1,1]}',
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

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == "FAILED"
    assert (
        fetch_response.json()["remark"]
        == "Parser artifact does not match the canonical content_list contract."
    )
    assert not any(
        upload.object_key == build_logical_tables_object_key(task_id)
        for upload in test_app.state.object_storage_client.uploads
    )


async def test_extractor_worker_marks_failed_when_logical_tables_upload_fails(
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
        data=build_multi_page_content_list(),
        content_type="application/json",
    )
    test_app.state.object_storage_client.upload_failures_remaining = 1
    test_app.state.queue_client.extractor_messages.append(
        ExtractorTaskMessage(
            task_id=payload["task_id"],
            doc_type="ANNUAL_REPORT",
            bucket=bucket,
            content_list_object_key=content_key,
        )
    )

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == "FAILED"
    assert (
        fetch_response.json()["remark"]
        == "Failed to persist logical tables artifact to object storage."
    )
    assert not any(
        upload.object_key == build_logical_tables_object_key(task_id)
        for upload in test_app.state.object_storage_client.uploads
    )


async def test_extractor_worker_marks_failed_when_llm_fallback_errors(
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
    test_app.state.llm_fallback_client.raise_error = True

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    fetch_response = await async_client.get(f"/api/v1/tasks/{payload['task_id']}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == "FAILED"
    assert fetch_response.json()["remark"] == "Failed to call LLM fallback endpoint."
    assert test_app.state.result_repository.rows == []


async def test_extractor_worker_skips_logical_table_upload_for_missing_task(test_app) -> None:
    task_id = 999999
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
            task_id=str(task_id),
            doc_type="ANNUAL_REPORT",
            bucket=bucket,
            content_list_object_key=content_key,
        )
    )

    worker = build_extractor_worker(test_app)
    assert await worker.process_next_message(timeout_seconds=0) is True

    assert not any(
        upload.object_key == build_logical_tables_object_key(task_id)
        for upload in test_app.state.object_storage_client.uploads
    )
    assert test_app.state.result_repository.rows == []
