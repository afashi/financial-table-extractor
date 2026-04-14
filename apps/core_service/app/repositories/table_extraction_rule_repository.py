from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule


class TableExtractionRuleRepository:
    async def list_active_by_doc_type(
        self,
        session: AsyncSession,
        *,
        doc_type: str,
    ) -> list[TableExtractionRule]:
        statement = (
            select(TableExtractionRule)
            .where(
                TableExtractionRule.doc_type == doc_type,
                TableExtractionRule.is_active == "1",
            )
            .order_by(TableExtractionRule.id.asc())
        )
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def list_rules_missing_vectors(
        self,
        session: AsyncSession,
    ) -> list[TableExtractionRule]:
        statement = (
            select(TableExtractionRule)
            .where(TableExtractionRule.semantic_vector.is_(None))
            .order_by(TableExtractionRule.id.asc())
        )
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def update_semantic_vectors(
        self,
        session: AsyncSession,
        *,
        pairs: list[tuple[TableExtractionRule, list[float]]],
    ) -> None:
        for rule, vector in pairs:
            rule.semantic_vector = vector
        await session.flush()
