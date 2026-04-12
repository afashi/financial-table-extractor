from decimal import Decimal

from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.routing import RouteDecision


class FastTrackExtractor:
    def extract(self, *, decision: RouteDecision) -> ExtractionOutcome:
        if decision.matched_table is None:
            raise ValueError("FAST_TRACK decision requires a matched logical table.")

        bbox = [
            {
                "page": segment.page_idx,
                "x0": segment.bbox[0],
                "y0": segment.bbox[1],
                "x1": segment.bbox[2],
                "y1": segment.bbox[3],
            }
            for segment in decision.matched_table.segments
        ]
        return ExtractionOutcome(
            data_status="SUCCESS",
            extraction_route="FAST_TRACK",
            table_data={
                "headers": list(decision.matched_table.header),
                "rows": list(decision.matched_table.rows),
            },
            start_page=decision.matched_table.start_page,
            end_page=decision.matched_table.end_page,
            bbox=bbox,
            confidence_score=Decimal("95.00"),
            needs_review="0",
            remark=f"Rule matched logical table with score {decision.best_score:.3f}.",
        )
