from decimal import Decimal

from apps.core_service.app.schemas.extraction import ExtractionOutcome

_BASE_SCORE = Decimal("100.00")
_SLOW_TRACK_PENALTY = Decimal("15.00")
_MISSING_UNIT_PENALTY = Decimal("10.00")
_MIN_SCORE = Decimal("0.00")
_REVIEW_THRESHOLD = Decimal("85.00")


class ConfidenceScorer:
    def apply(self, *, outcome: ExtractionOutcome) -> ExtractionOutcome:
        score = _BASE_SCORE

        if outcome.extraction_route == "SLOW_TRACK":
            score -= _SLOW_TRACK_PENALTY

        if outcome.data_status == "SUCCESS" and outcome.unit is None:
            score -= _MISSING_UNIT_PENALTY

        if score < _MIN_SCORE:
            score = _MIN_SCORE

        needs_review = "1" if score < _REVIEW_THRESHOLD else "0"

        return outcome.model_copy(
            update={
                "confidence_score": score,
                "needs_review": needs_review,
            }
        )
