from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ExtractionOutcome(BaseModel):
    data_status: Literal["SUCCESS", "NOT_DISCLOSED", "NOT_FIND"]
    extraction_route: Literal["FAST_TRACK", "SLOW_TRACK"] | None = None
    table_data: dict[str, object] | None = None
    start_page: int | None = None
    end_page: int | None = None
    bbox: list[dict[str, int | float]] | None = None
    confidence_score: Decimal
    needs_review: str = "0"
    remark: str | None = None
    unit: str | None = None
    currency: str | None = None
