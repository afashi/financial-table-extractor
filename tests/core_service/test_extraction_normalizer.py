from decimal import Decimal

from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment
from apps.core_service.app.schemas.routing import RouteDecision
from apps.core_service.app.services.extraction_normalizer import ExtractionNormalizer

SECTION_PATH = ["\u7ba1\u7406\u5c42\u8ba8\u8bba\u4e0e\u5206\u6790", "\u4e3b\u8425\u4e1a\u52a1\u5206\u6790"]
HEADER = ["\u5206\u90e8", "\u6536\u5165"]
FAST_ROWS = [["\u5883\u5185", "-"], ["\u5883\u5916", "0"], ["\u5176\u4ed6", "  "]]


def test_normalizer_extracts_unit_currency_and_normalizes_table_cells() -> None:
    decision = RouteDecision(
        decision="FAST_TRACK",
        best_score=Decimal("0.950"),
        matched_path=[SECTION_PATH[0], "\u4eba\u6c11\u5e01\u5143"],
        matched_table=LogicalTable(
            logical_table_id="lt-1",
            start_page=6,
            end_page=6,
            header=HEADER,
            rows=FAST_ROWS,
            section_path=SECTION_PATH,
            segments=[
                LogicalTableSegment(
                    page_idx=6,
                    block_index=2,
                    bbox=[0.0, 40.0, 300.0, 180.0],
                )
            ],
            context_before=[],
        ),
        context_blocks=["\u5355\u4f4d\uff1a\u4eba\u6c11\u5e01\u5143"],
        remark="Matched logical table by path fingerprint and anchor rules.",
    )
    outcome = ExtractionOutcome(
        data_status="SUCCESS",
        extraction_route="FAST_TRACK",
        table_data={
            "headers": HEADER,
            "rows": FAST_ROWS,
        },
        start_page=6,
        end_page=6,
        confidence_score=Decimal("95.00"),
        needs_review="0",
    )
    content_blocks = [
        ArtifactContentBlock(
            type="text",
            page_idx=6,
            bbox=[0.0, 0.0, 300.0, 20.0],
            text="\u5355\u4f4d\uff1a\u4eba\u6c11\u5e01\u4e07\u5143",
        ),
        ArtifactContentBlock(
            type="text",
            page_idx=10,
            bbox=[0.0, 0.0, 300.0, 20.0],
            text="\u5355\u4f4d\uff1a\u4eba\u6c11\u5e01\u5143",
        ),
    ]

    normalized = ExtractionNormalizer().normalize(
        outcome=outcome,
        decision=decision,
        content_blocks=content_blocks,
    )

    assert normalized.unit == "CNY_TEN_THOUSAND"
    assert normalized.currency == "CNY"
    assert normalized.table_data == {
        "headers": HEADER,
        "rows": [["\u5883\u5185", None], ["\u5883\u5916", "0.00"], ["\u5176\u4ed6", None]],
    }


def test_normalizer_keeps_not_disclosed_as_empty_fields() -> None:
    decision = RouteDecision(
        decision="SLOW_TRACK",
        best_score=Decimal("0.700"),
        matched_path=["\u9644\u6ce8", "\u4eba\u6c11\u5e01\u4e07\u5143"],
        context_blocks=["\u5355\u4f4d\uff1a\u4eba\u6c11\u5e01\u4e07\u5143"],
        remark="Use fallback.",
    )
    outcome = ExtractionOutcome(
        data_status="NOT_DISCLOSED",
        extraction_route="SLOW_TRACK",
        table_data=None,
        confidence_score=Decimal("60.00"),
        needs_review="1",
    )
    content_blocks = [
        ArtifactContentBlock(
            type="text",
            page_idx=0,
            bbox=[0.0, 0.0, 300.0, 20.0],
            text="\u5355\u4f4d\uff1a\u4eba\u6c11\u5e01\u4e07\u5143",
        )
    ]

    normalized = ExtractionNormalizer().normalize(
        outcome=outcome,
        decision=decision,
        content_blocks=content_blocks,
    )

    assert normalized.table_data is None
    assert normalized.unit is None
    assert normalized.currency is None
