import re
from decimal import Decimal

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.logical_table import LogicalTable
from apps.core_service.app.schemas.routing import RouteDecision


class TableRouter:
    def route(
        self,
        *,
        rule: TableExtractionRule,
        logical_tables: list[LogicalTable],
        content_blocks: list[ArtifactContentBlock],
    ) -> RouteDecision:
        section_tables = [
            table
            for table in logical_tables
            if self._path_matches(rule.path_fingerprints, table.section_path)
        ]
        if section_tables:
            scored_tables = [
                (table, self._candidate_score(rule=rule, table=table))
                for table in section_tables
            ]
            best_table, best_score = max(scored_tables, key=lambda item: item[1])
            if best_score >= self._threshold(rule):
                return RouteDecision(
                    decision="FAST_TRACK",
                    best_score=best_score,
                    matched_path=list(best_table.section_path),
                    matched_table=best_table,
                    context_blocks=list(best_table.context_before),
                    remark="Matched logical table by path fingerprint and anchor rules.",
                )
            return RouteDecision(
                decision="SLOW_TRACK",
                best_score=best_score,
                matched_path=list(best_table.section_path),
                matched_table=None,
                context_blocks=self._section_context(
                    rule=rule,
                    content_blocks=content_blocks,
                    logical_tables=section_tables,
                ),
                remark="Matched section fingerprint but no logical table reached the minimum score.",
            )

        text_only_context = self._text_only_context(rule=rule, content_blocks=content_blocks)
        if text_only_context:
            return RouteDecision(
                decision="SLOW_TRACK",
                best_score=Decimal("0.000"),
                matched_path=list(rule.path_fingerprints),
                matched_table=None,
                context_blocks=text_only_context,
                remark="Matched section heading in text blocks but did not find a standard logical table.",
            )

        return RouteDecision(
            decision="NOT_FIND",
            best_score=Decimal("0.000"),
            matched_path=[],
            matched_table=None,
            context_blocks=[],
            remark="Section fingerprint was not found in the parsed artifact.",
        )

    def _candidate_score(
        self,
        *,
        rule: TableExtractionRule,
        table: LogicalTable,
    ) -> Decimal:
        anchor_rule = rule.anchor_rule or {}
        logic_match = anchor_rule.get("logic_match", {})
        regex_match = anchor_rule.get("regex_match", {})
        header_set = {cell for cell in table.header if cell}
        context_text = " ".join([*table.section_path, *table.context_before])
        score = Decimal("0.350")

        required_headers = logic_match.get("required_headers", [])
        if isinstance(required_headers, list) and all(
            isinstance(header, str) and header in header_set for header in required_headers
        ):
            score += Decimal("0.350")

        required_keywords = logic_match.get("required_context_keywords", [])
        if isinstance(required_keywords, list) and all(
            isinstance(keyword, str) and keyword in context_text for keyword in required_keywords
        ):
            score += Decimal("0.150")

        title_pattern = regex_match.get("title_pattern")
        if isinstance(title_pattern, str) and re.search(title_pattern, context_text):
            score += Decimal("0.100")

        if rule.semantic_anchor_text:
            score += self._semantic_overlap_bonus(
                anchor_text=rule.semantic_anchor_text,
                context_text=context_text,
            )

        return min(score, Decimal("1.000"))

    def _semantic_overlap_bonus(
        self,
        *,
        anchor_text: str,
        context_text: str,
    ) -> Decimal:
        anchor_tokens = {token for token in anchor_text.split() if token}
        context_tokens = {token for token in context_text.split() if token}
        if not anchor_tokens or not context_tokens:
            return Decimal("0.000")
        overlap_ratio = len(anchor_tokens & context_tokens) / len(anchor_tokens)
        return Decimal(str(round(overlap_ratio * 0.050, 3)))

    def _threshold(self, rule: TableExtractionRule) -> Decimal:
        return rule.min_match_score or Decimal("0.850")

    def _path_matches(
        self,
        path_fingerprint: list[str],
        section_path: list[str],
    ) -> bool:
        return tuple(item.strip() for item in path_fingerprint) == tuple(
            item.strip() for item in section_path
        )

    def _section_context(
        self,
        *,
        rule: TableExtractionRule,
        content_blocks: list[ArtifactContentBlock],
        logical_tables: list[LogicalTable],
    ) -> list[str]:
        page_numbers = {
            segment.page_idx for table in logical_tables for segment in table.segments
        }
        texts = [
            block.text.strip()
            for block in content_blocks
            if block.type == "text"
            and block.text
            and block.page_idx in page_numbers
            and block.text.strip()
        ]
        if texts:
            return texts
        return list(rule.path_fingerprints)

    def _text_only_context(
        self,
        *,
        rule: TableExtractionRule,
        content_blocks: list[ArtifactContentBlock],
    ) -> list[str]:
        if not rule.path_fingerprints:
            return []
        leaf_fingerprint = rule.path_fingerprints[-1].strip()
        if not leaf_fingerprint:
            return []
        return [
            block.text.strip()
            for block in content_blocks
            if block.type == "text"
            and block.text
            and leaf_fingerprint in block.text
            and block.text.strip()
        ]
