from collections.abc import Sequence

from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.shared.enums.task_status import TaskStatus


class TaskStatusEvaluator:
    def evaluate(self, *, outcomes: Sequence[ExtractionOutcome]) -> TaskStatus:
        for outcome in outcomes:
            if outcome.needs_review == "1":
                return TaskStatus.PENDING_REVIEW
        return TaskStatus.COMPLETED
