from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import delete

from apps.core_service.app.clients.database import DatabaseClient
from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.repositories.extracted_result_repository import (
    ExtractedResultRepository,
)
from apps.core_service.app.repositories.table_extraction_rule_repository import (
    TableExtractionRuleRepository,
)
from apps.core_service.app.schemas.extraction import ExtractionOutcome


@pytest.fixture
async def async_session() -> AsyncIterator:
    client = DatabaseClient(
        "postgresql+asyncpg://postgres:postgres@localhost:25432/financial_table_extractor"
    )
    async with client.session_factory() as session:
        await session.execute(delete(ExtractedResult))
        await session.execute(delete(TableExtractionRule))
        await session.commit()
        yield session
        await session.execute(delete(ExtractedResult))
        await session.execute(delete(TableExtractionRule))
        await session.commit()
    await client.dispose()


async def test_rule_listing_and_placeholder_upsert(async_session) -> None:
    active_rule = TableExtractionRule(
        id=2001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule={"logic_match": {"required_headers": ["分部", "收入"]}},
        semantic_anchor_text="主营业务收入 管理层讨论与分析 主营业务分析",
        min_match_score=Decimal("0.900"),
        is_active="1",
    )
    inactive_rule = TableExtractionRule(
        id=2002,
        doc_type="ANNUAL_REPORT",
        target_table_code="deprecated_rule",
        target_table_name="废弃规则",
        path_fingerprints=["旧章节"],
        anchor_rule={},
        semantic_anchor_text=None,
        min_match_score=None,
        is_active="0",
    )
    async_session.add_all([active_rule, inactive_rule])
    await async_session.commit()

    rule_repo = TableExtractionRuleRepository()
    result_repo = ExtractedResultRepository()

    active_rules = await rule_repo.list_active_by_doc_type(
        async_session,
        doc_type="ANNUAL_REPORT",
    )
    assert [rule.target_table_code for rule in active_rules] == ["main_business_revenue"]

    result = await result_repo.upsert_placeholder_not_find(
        async_session,
        result_id=9001,
        task_id=1001,
        rule=active_rule,
        remark="Extraction backbone placeholder result.",
    )
    await async_session.commit()

    assert result.id == 9001
    assert result.task_id == 1001
    assert result.rule_id == 2001
    assert result.target_table_code == "main_business_revenue"
    assert result.data_status == "NOT_FIND"
    assert result.table_data is None
    assert result.extraction_route is None
    assert result.confidence_score == Decimal("100.00")
    assert result.needs_review == "0"


async def test_result_upsert_persists_fast_track_payload(async_session) -> None:
    active_rule = TableExtractionRule(
        id=2001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule={"logic_match": {"required_headers": ["分部", "收入"]}},
        semantic_anchor_text="主营业务收入 管理层讨论与分析 主营业务分析",
        min_match_score=Decimal("0.900"),
        is_active="1",
    )
    async_session.add(active_rule)
    await async_session.commit()

    result_repo = ExtractedResultRepository()
    outcome = ExtractionOutcome(
        data_status="SUCCESS",
        extraction_route="FAST_TRACK",
        table_data={"headers": ["分部", "收入"], "rows": [["境内", "100"]]},
        start_page=3,
        end_page=3,
        bbox=[{"page": 3, "x0": 0.0, "y0": 40.0, "x1": 300.0, "y1": 180.0}],
        confidence_score=Decimal("95.00"),
        needs_review="0",
        remark="Rule matched logical table with score 0.950.",
    )

    result = await result_repo.upsert_result(
        async_session,
        result_id=9001,
        task_id=1001,
        rule=active_rule,
        outcome=outcome,
    )
    await async_session.commit()

    assert result.data_status == "SUCCESS"
    assert result.extraction_route == "FAST_TRACK"
    assert result.table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", "100"]],
    }
    assert result.start_page == 3
    assert result.end_page == 3
