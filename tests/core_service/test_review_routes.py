from decimal import Decimal

from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.task import Task
from apps.shared.enums.task_status import TaskStatus


async def _seed_review_state(test_app) -> None:
    task = Task(
        id=1001,
        doc_type="ANNUAL_REPORT",
        file_name="annual.pdf",
        file_hash="hash-1",
        file_size=128,
        status=TaskStatus.PENDING_REVIEW,
        remark=None,
    )
    await test_app.state.task_repository.create(None, task)
    test_app.state.result_repository.rows.append(
        ExtractedResult(
            id=2001,
            task_id=1001,
            rule_id=3001,
            target_table_code="main_business_revenue",
            unit="CNY_TEN_THOUSAND",
            currency="CNY",
            extraction_route="SLOW_TRACK",
            data_status="SUCCESS",
            table_data={"headers": ["分部", "收入"], "rows": [["境内", "100"]]},
            fix_table_data=None,
            start_page=3,
            end_page=3,
            bbox=None,
            confidence_score=Decimal("75.00"),
            needs_review="1",
            remark="Missing unit in source table.",
        )
    )


async def test_get_review_queue(async_client, test_app) -> None:
    await _seed_review_state(test_app)

    response = await async_client.get("/api/v1/review/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == "1001"
    assert payload[0]["pending_result_count"] == 1


async def test_get_task_results(async_client, test_app) -> None:
    await _seed_review_state(test_app)

    response = await async_client.get("/api/v1/tasks/1001/results")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["result_id"] == "2001"
    assert payload[0]["target_table_code"] == "main_business_revenue"
