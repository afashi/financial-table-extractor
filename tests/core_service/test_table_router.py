from decimal import Decimal

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment
from apps.core_service.app.services.table_router import TableRouter


def _rule(
    *,
    headers: list[str],
    keywords: list[str],
    title_pattern: str | None = None,
) -> TableExtractionRule:
    anchor_rule: dict[str, object] = {
        "logic_match": {
            "required_headers": headers,
            "required_context_keywords": keywords,
        }
    }
    if title_pattern is not None:
        anchor_rule["regex_match"] = {"title_pattern": title_pattern}
    return TableExtractionRule(
        id=3001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule=anchor_rule,
        semantic_anchor_text="主营业务收入 分部 收入",
        min_match_score=Decimal("0.850"),
        is_active="1",
    )


def _logical_table(
    *,
    header: list[str],
    rows: list[list[str]],
    context_before: list[str],
) -> LogicalTable:
    return LogicalTable(
        logical_table_id="lt-1",
        start_page=3,
        end_page=3,
        header=header,
        rows=rows,
        section_path=["管理层讨论与分析", "主营业务分析"],
        segments=[
            LogicalTableSegment(
                page_idx=3,
                block_index=4,
                bbox=[0.0, 40.0, 300.0, 180.0],
            )
        ],
        context_before=context_before,
    )


def _text_block(*, page_idx: int, text: str) -> ArtifactContentBlock:
    return ArtifactContentBlock(
        type="text",
        page_idx=page_idx,
        bbox=[0.0, 0.0, 300.0, 24.0],
        text=text,
    )


def test_router_returns_fast_track_when_path_and_headers_match() -> None:
    decision = TableRouter().route(
        rule=_rule(headers=["分部", "收入"], keywords=["主营业务"]),
        logical_tables=[
            _logical_table(
                header=["分部", "收入"],
                rows=[["境内", "100"]],
                context_before=["主营业务收入表"],
            )
        ],
        content_blocks=[_text_block(page_idx=3, text="主营业务分析")],
    )

    assert decision.decision == "FAST_TRACK"
    assert decision.matched_table is not None
    assert decision.matched_table.logical_table_id == "lt-1"
    assert decision.best_score >= Decimal("0.850")


def test_router_returns_slow_track_when_section_exists_but_table_score_is_too_low() -> None:
    decision = TableRouter().route(
        rule=_rule(headers=["分部", "营业收入"], keywords=["主营业务"]),
        logical_tables=[
            _logical_table(
                header=["分部", "收入"],
                rows=[["境内", "100"]],
                context_before=["主营业务分析", "公司主营业务收入如下"],
            )
        ],
        content_blocks=[
            _text_block(page_idx=3, text="主营业务分析"),
            _text_block(page_idx=3, text="公司主营业务收入如下。"),
        ],
    )

    assert decision.decision == "SLOW_TRACK"
    assert decision.matched_table is None
    assert "公司主营业务收入如下。" in decision.context_blocks


def test_router_returns_not_find_when_no_section_fingerprint_is_present() -> None:
    decision = TableRouter().route(
        rule=_rule(headers=["分部", "收入"], keywords=["主营业务"]),
        logical_tables=[],
        content_blocks=[_text_block(page_idx=0, text="公司治理")],
    )

    assert decision.decision == "NOT_FIND"
    assert decision.matched_table is None
    assert decision.context_blocks == []
