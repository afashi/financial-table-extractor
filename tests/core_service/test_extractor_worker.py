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
