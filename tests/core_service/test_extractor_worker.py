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
