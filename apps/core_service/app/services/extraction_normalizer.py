import re
from collections.abc import Iterable

from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.extraction import ExtractionOutcome
from apps.core_service.app.schemas.normalization import NormalizedCurrency, NormalizedUnit
from apps.core_service.app.schemas.routing import RouteDecision

_CURRENCY_CNY: NormalizedCurrency = "CNY"

_PATTERN_CNY_TEN_THOUSAND = re.compile(
    r"\u4eba\u6c11\u5e01\s*\u4e07\u5143"
)
_PATTERN_CNY_YUAN = re.compile(r"\u4eba\u6c11\u5e01\s*\u5143")
_PATTERN_UNIT_YUAN = re.compile(r"\u5355\u4f4d\s*[:\uff1a]\s*\u5143")


class ExtractionNormalizer:
    def normalize(
        self,
        *,
        outcome: ExtractionOutcome,
        decision: RouteDecision,
        content_blocks: list[ArtifactContentBlock],
    ) -> ExtractionOutcome:
        normalized_table_data = self._normalize_table_data(outcome.table_data)
        unit, currency = self._normalize_metadata(
            outcome=outcome,
            decision=decision,
            content_blocks=content_blocks,
        )
        return outcome.model_copy(
            update={
                "table_data": normalized_table_data,
                "unit": unit,
                "currency": currency,
            }
        )

    def _normalize_table_data(
        self,
        table_data: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if table_data is None:
            return None

        rows = table_data.get("rows")
        if not isinstance(rows, list):
            return dict(table_data)

        normalized_rows: list[object] = []
        for row in rows:
            if not isinstance(row, list):
                normalized_rows.append(row)
                continue
            normalized_rows.append([self._normalize_cell(cell) for cell in row])

        normalized_table_data = dict(table_data)
        normalized_table_data["rows"] = normalized_rows
        return normalized_table_data

    def _normalize_cell(self, cell: object) -> str | None:
        if cell is None:
            return None

        text = str(cell).strip()
        if text in {"", "-"}:
            return None
        if text in {"0", "0.0", "0.00"}:
            return "0.00"
        return text

    def _normalize_metadata(
        self,
        *,
        outcome: ExtractionOutcome,
        decision: RouteDecision,
        content_blocks: list[ArtifactContentBlock],
    ) -> tuple[NormalizedUnit | None, NormalizedCurrency | None]:
        if outcome.data_status != "SUCCESS":
            return None, None

        for text in self._candidate_texts(decision=decision, content_blocks=content_blocks):
            unit_currency = self._match_unit_currency(text)
            if unit_currency is not None:
                return unit_currency
        return None, None

    def _candidate_texts(
        self,
        *,
        decision: RouteDecision,
        content_blocks: list[ArtifactContentBlock],
    ) -> Iterable[str]:
        matched_pages = self._matched_pages(decision)
        if matched_pages:
            for block in content_blocks:
                if (
                    block.type == "text"
                    and block.page_idx in matched_pages
                    and block.text is not None
                ):
                    text = block.text.strip()
                    if text:
                        yield text

        for text in decision.context_blocks:
            normalized = text.strip()
            if normalized:
                yield normalized

        for text in decision.matched_path:
            normalized = text.strip()
            if normalized:
                yield normalized

    def _matched_pages(self, decision: RouteDecision) -> set[int]:
        if decision.matched_table is None:
            return set()

        pages = {segment.page_idx for segment in decision.matched_table.segments}
        if pages:
            return pages

        start_page = decision.matched_table.start_page
        end_page = decision.matched_table.end_page
        if start_page > end_page:
            return set()
        return set(range(start_page, end_page + 1))

    def _match_unit_currency(
        self, text: str
    ) -> tuple[NormalizedUnit, NormalizedCurrency] | None:
        if _PATTERN_CNY_TEN_THOUSAND.search(text):
            return "CNY_TEN_THOUSAND", _CURRENCY_CNY
        if _PATTERN_CNY_YUAN.search(text):
            return "CNY_YUAN", _CURRENCY_CNY
        if _PATTERN_UNIT_YUAN.search(text):
            return "CNY_YUAN", _CURRENCY_CNY
        return None
