from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from apps.core_service.app.schemas.logical_table import LogicalTable


class RoutingCandidate(BaseModel):
    logical_table: LogicalTable
    score: Decimal
    matched_headers: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    matched_title: str | None = None


class RouteDecision(BaseModel):
    decision: Literal["FAST_TRACK", "SLOW_TRACK", "NOT_FIND"]
    best_score: Decimal = Decimal("0.000")
    matched_path: list[str] = Field(default_factory=list)
    matched_table: LogicalTable | None = None
    context_blocks: list[str] = Field(default_factory=list)
    remark: str
