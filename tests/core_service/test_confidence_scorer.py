from decimal import Decimal

from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.services.confidence_scorer import ConfidenceScorer
from apps.core_service.app.services.task_status_evaluator import TaskStatusEvaluator
from apps.shared.enums.task_status import TaskStatus


def _outcome(
    *,
    data_status: str,
    extraction_route: str,
    unit: str | None,
    needs_review: str = "0",
) -> ExtractionOutcome:
    return ExtractionOutcome(
        data_status=data_status,
        extraction_route=extraction_route,
        table_data=None,
        confidence_score=Decimal("0.00"),
        needs_review=needs_review,
        unit=unit,
        currency="CNY" if unit is not None else None,
    )


def test_fast_track_success_with_unit_keeps_full_score() -> None:
    scored = ConfidenceScorer().apply(
        outcome=_outcome(
            data_status="SUCCESS",
            extraction_route="FAST_TRACK",
            unit="CNY_YUAN",
        )
    )

    assert scored.confidence_score == Decimal("100.00")
    assert scored.needs_review == "0"


def test_slow_track_success_without_unit_marks_review() -> None:
    scored = ConfidenceScorer().apply(
        outcome=_outcome(
            data_status="SUCCESS",
            extraction_route="SLOW_TRACK",
            unit=None,
        )
    )

    assert scored.confidence_score == Decimal("75.00")
    assert scored.needs_review == "1"


def test_slow_track_not_disclosed_without_unit_stays_at_85_without_review() -> None:
    scored = ConfidenceScorer().apply(
        outcome=_outcome(
            data_status="NOT_DISCLOSED",
            extraction_route="SLOW_TRACK",
            unit=None,
        )
    )

    assert scored.confidence_score == Decimal("85.00")
    assert scored.needs_review == "0"


def test_evaluator_returns_pending_review_when_any_outcome_needs_review() -> None:
    status = TaskStatusEvaluator().evaluate(
        outcomes=[
            _outcome(
                data_status="SUCCESS",
                extraction_route="FAST_TRACK",
                unit="CNY_YUAN",
                needs_review="0",
            ),
            _outcome(
                data_status="SUCCESS",
                extraction_route="SLOW_TRACK",
                unit=None,
                needs_review="1",
            ),
        ]
    )

    assert status is TaskStatus.PENDING_REVIEW
