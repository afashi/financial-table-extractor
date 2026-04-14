from decimal import Decimal

from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.task import Task
from apps.core_service.app.services.review_service import ReviewService
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


async def test_review_service_lists_pending_review_tasks(test_app) -> None:
    await _seed_review_state(test_app)
    service = ReviewService(
        session=test_app.state.database_client.session_factory(),
        task_repository=test_app.state.task_repository,
        result_repository=test_app.state.result_repository,
    )

    queue = await service.list_pending_review_tasks()

    assert len(queue) == 1
    assert queue[0].task_id == "1001"
    assert queue[0].pending_result_count == 1
    assert queue[0].target_table_codes == ["main_business_revenue"]


async def test_review_service_returns_task_results(test_app) -> None:
    await _seed_review_state(test_app)
    service = ReviewService(
        session=test_app.state.database_client.session_factory(),
        task_repository=test_app.state.task_repository,
        result_repository=test_app.state.result_repository,
    )

    results = await service.get_task_results(task_id=1001)

    assert results[0].result_id == "2001"
    assert results[0].needs_review == "1"
    assert results[0].fix_table_data is None


async def test_review_service_applies_fix_and_clears_task_review_flag(test_app) -> None:
    await _seed_review_state(test_app)
    service = ReviewService(
        session=test_app.state.database_client.session_factory(),
        task_repository=test_app.state.task_repository,
        result_repository=test_app.state.result_repository,
    )

    updated = await service.apply_fix(
        task_id=1001,
        result_id=2001,
        fix_table_data={"headers": ["分部", "收入"], "rows": [["境内", "100.00"]]},
        remark="人工复核确认收入口径。",
    )

    assert updated.fix_table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", "100.00"]],
    }
    assert updated.needs_review == "0"
    task = await test_app.state.task_repository.get_by_id(None, 1001)
    assert task.status == TaskStatus.COMPLETED
