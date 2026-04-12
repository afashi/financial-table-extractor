from decimal import Decimal

import pytest

from apps.core_service.app.clients.llm_fallback import (
    DisabledLLMFallbackClient,
    HttpLLMFallbackClient,
)
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.routing import RouteDecision


def _rule() -> TableExtractionRule:
    return TableExtractionRule(
        id=3001,
        doc_type="ANNUAL_REPORT",
        target_table_code="main_business_revenue",
        target_table_name="主营业务收入",
        path_fingerprints=["管理层讨论与分析", "主营业务分析"],
        anchor_rule={},
        semantic_anchor_text="主营业务收入",
        min_match_score=Decimal("0.850"),
        is_active="1",
    )


@pytest.mark.asyncio
async def test_disabled_fallback_returns_not_disclosed() -> None:
    client = DisabledLLMFallbackClient()

    outcome = await client.extract(
        rule=_rule(),
        decision=RouteDecision(
            decision="SLOW_TRACK",
            matched_path=["管理层讨论与分析", "主营业务分析"],
            context_blocks=["主营业务分析", "本期未披露主营业务收入明细。"],
            remark="Matched section fingerprint but no logical table reached the minimum score.",
        ),
    )

    assert outcome.data_status == "NOT_DISCLOSED"
    assert outcome.extraction_route == "SLOW_TRACK"


@pytest.mark.asyncio
async def test_http_fallback_parses_success_response() -> None:
    async def sender(
        *,
        endpoint: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, object]:
        assert endpoint == "http://llm.test/extract"
        assert headers["Content-Type"] == "application/json"
        assert payload["target_table_code"] == "main_business_revenue"
        assert payload["context_blocks"] == ["主营业务分析", "公司主营业务收入如下。"]
        assert timeout_seconds == 30.0
        return {
            "data_status": "SUCCESS",
            "table_data": {
                "headers": ["分部", "收入"],
                "rows": [["境内", "100"]],
            },
            "remark": "Extracted from fallback context.",
        }

    client = HttpLLMFallbackClient(
        endpoint="http://llm.test/extract",
        model_name="fallback-test",
        timeout_seconds=30.0,
        sender=sender,
    )

    outcome = await client.extract(
        rule=_rule(),
        decision=RouteDecision(
            decision="SLOW_TRACK",
            matched_path=["管理层讨论与分析", "主营业务分析"],
            context_blocks=["主营业务分析", "公司主营业务收入如下。"],
            remark="Matched section fingerprint but no logical table reached the minimum score.",
        ),
    )

    assert outcome.data_status == "SUCCESS"
    assert outcome.extraction_route == "SLOW_TRACK"
    assert outcome.table_data == {
        "headers": ["分部", "收入"],
        "rows": [["境内", "100"]],
    }
