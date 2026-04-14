import re
from decimal import Decimal

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.logical_table import LogicalTable
from apps.core_service.app.schemas.routing import RouteDecision
from apps.core_service.app.schemas.toc import TocDraftNode


class _ZeroEmbeddingClient:
    async def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class TableRouter:
    def __init__(self, *, embedding_client=None) -> None:
        self._embedding_client = embedding_client or _ZeroEmbeddingClient()

    async def route(
        self,
        *,
        rule: TableExtractionRule,
        toc_nodes: list[TocDraftNode],
        logical_tables: list[LogicalTable],
        content_blocks: list[ArtifactContentBlock],
    ) -> RouteDecision:
        if not self._toc_contains_path(rule.path_fingerprints, toc_nodes):
            return RouteDecision(
                decision="NOT_FIND",
                best_score=Decimal("0.000"),
                matched_path=[],
                matched_table=None,
                context_blocks=[],
                remark="Section fingerprint was not found in the persisted TOC tree.",
                semantic_match_score=Decimal("0.000"),
            )

        section_tables = [
            table
            for table in logical_tables
            if self._path_matches(rule.path_fingerprints, table.section_path)
        ]
        if not section_tables:
            return RouteDecision(
                decision="SLOW_TRACK",
                best_score=Decimal("0.000"),
                matched_path=list(rule.path_fingerprints),
                matched_table=None,
                context_blocks=self._text_only_context(rule=rule, content_blocks=content_blocks),
                remark="TOC matched but no standard logical table was found in the section.",
                semantic_match_score=Decimal("0.000"),
            )

        candidate_vectors = self._empty_vectors(count=len(section_tables))
        if rule.semantic_vector:
            candidate_texts = [self._candidate_text(table) for table in section_tables]
            candidate_vectors = await self._embedding_client.encode(candidate_texts)
        scored_tables: list[tuple[LogicalTable, Decimal, Decimal]] = []
        for table, vector in zip(section_tables, candidate_vectors, strict=True):
            deterministic_score = self._candidate_score(rule=rule, table=table)
            semantic_score = self._cosine_similarity(rule.semantic_vector, vector)
            total_score = min(
                deterministic_score + (semantic_score * Decimal("0.350")),
                Decimal("1.000"),
            )
            scored_tables.append((table, total_score, semantic_score))

        best_table, best_score, semantic_score = max(scored_tables, key=lambda item: item[1])
        if best_score >= self._threshold(rule):
            return RouteDecision(
                decision="FAST_TRACK",
                best_score=best_score,
                matched_path=list(best_table.section_path),
                matched_table=best_table,
                context_blocks=list(best_table.context_before),
                remark="Matched logical table by TOC, anchor rules, and vector score.",
                semantic_match_score=semantic_score,
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
            remark="Section matched but no logical table cleared the combined threshold.",
            semantic_match_score=semantic_score,
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

        return min(score, Decimal("1.000"))

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

    def _toc_contains_path(
        self,
        path_fingerprint: list[str],
        toc_nodes: list[TocDraftNode],
    ) -> bool:
        parent_title: str | None = None
        parent_id: int | None = None
        for level, title in enumerate(path_fingerprint, start=1):
            title = title.strip()
            if not title:
                return False
            node = next(
                (
                    item
                    for item in toc_nodes
                    if item.level == level
                    and item.title.strip() == title
                    and self._parent_matches(
                        item,
                        parent_title=parent_title,
                        parent_id=parent_id,
                    )
                ),
                None,
            )
            if node is None:
                return False
            parent_title = node.title
            parent_id = getattr(node, "id", None)
        return bool(path_fingerprint)

    def _candidate_text(self, table: LogicalTable) -> str:
        return " ".join([*table.section_path, *table.context_before, *table.header]).strip()

    def _cosine_similarity(
        self,
        lhs: list[float] | None,
        rhs: list[float] | None,
    ) -> Decimal:
        if not lhs or not rhs or len(lhs) != len(rhs):
            return Decimal("0.000")
        score = sum(left * right for left, right in zip(lhs, rhs, strict=True))
        return Decimal(f"{score:.3f}")

    def _parent_matches(
        self,
        node: TocDraftNode,
        *,
        parent_title: str | None,
        parent_id: int | None,
    ) -> bool:
        if hasattr(node, "parent_id"):
            return getattr(node, "parent_id") == parent_id
        return getattr(node, "parent_title", None) == parent_title

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

    def _empty_vectors(self, *, count: int) -> list[list[float]]:
        return [[0.0] for _ in range(count)]
