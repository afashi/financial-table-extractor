from decimal import Decimal

from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment
from apps.core_service.app.schemas.routing import RouteDecision
from apps.core_service.app.services.fast_track_extractor import FastTrackExtractor


def test_fast_track_extractor_builds_success_outcome() -> None:
    decision = RouteDecision(
        decision="FAST_TRACK",
        best_score=Decimal("0.950"),
        matched_path=["管理层讨论与分析", "主营业务分析"],
        matched_table=LogicalTable(
            logical_table_id="lt-1",
            start_page=3,
            end_page=4,
            header=["分部", "收入"],
            rows=[["境内", "100"], ["境外", "80"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
            segments=[
                LogicalTableSegment(
                    page_idx=3,
                    block_index=2,
                    bbox=[0.0, 40.0, 300.0, 180.0],
                ),
                LogicalTableSegment(
                    page_idx=4,
                    block_index=1,
                    bbox=[0.0, 36.0, 300.0, 170.0],
                ),
            ],
            context_before=["主营业务收入表"],
        ),
        context_blocks=["主营业务收入表"],
        remark="Matched logical table by path fingerprint and anchor rules.",
    )

    outcome = FastTrackExtractor().extract(decision=decision)

    assert outcome.data_status == "SUCCESS"
    assert outcome.extraction_route == "FAST_TRACK"
    assert outcome.start_page == 3
    assert outcome.end_page == 4
    assert outcome.table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", "100"], ["境外", "80"]],
    }
    assert outcome.bbox == [
        {"page": 3, "x0": 0.0, "y0": 40.0, "x1": 300.0, "y1": 180.0},
        {"page": 4, "x0": 0.0, "y0": 36.0, "x1": 300.0, "y1": 170.0},
    ]
