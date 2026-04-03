from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule


class ExtractedResultRepository:
    async def upsert_placeholder_not_find(
        self,
        session: AsyncSession,
        *,
        result_id: int,
        task_id: int,
        rule: TableExtractionRule,
        remark: str,
    ) -> ExtractedResult:
        statement = select(ExtractedResult).where(
            ExtractedResult.task_id == task_id,
            ExtractedResult.rule_id == rule.id,
        )
        existing = (await session.execute(statement)).scalar_one_or_none()
        if existing is None:
            existing = ExtractedResult(
                id=result_id,
                task_id=task_id,
                rule_id=rule.id,
                target_table_code=rule.target_table_code,
                data_status="NOT_FIND",
                confidence_score=Decimal("100.00"),
                needs_review="0",
            )
            session.add(existing)

        existing.unit = None
        existing.currency = None
        existing.extraction_route = None
        existing.table_data = None
        existing.fix_table_data = None
        existing.start_page = None
        existing.end_page = None
        existing.bbox = None
        existing.remark = remark
        existing.data_status = "NOT_FIND"
        existing.confidence_score = Decimal("100.00")
        existing.needs_review = "0"
        existing.update_time = datetime.now(UTC)
        await session.flush()
        await session.refresh(existing)
        return existing
