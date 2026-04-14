from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.db.models.extracted_result import ExtractedResult
from apps.core_service.app.db.models.table_extraction_rule import TableExtractionRule
from apps.core_service.app.schemas.extraction import ExtractionOutcome


class ExtractedResultRepository:
    async def upsert_result(
        self,
        session: AsyncSession,
        *,
        result_id: int,
        task_id: int,
        rule: TableExtractionRule,
        outcome: ExtractionOutcome,
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
                data_status=outcome.data_status,
                confidence_score=outcome.confidence_score,
                needs_review=outcome.needs_review,
            )
            session.add(existing)

        existing.unit = outcome.unit
        existing.currency = outcome.currency
        existing.extraction_route = outcome.extraction_route
        existing.table_data = outcome.table_data
        existing.fix_table_data = None
        existing.start_page = outcome.start_page
        existing.end_page = outcome.end_page
        existing.bbox = outcome.bbox
        existing.remark = outcome.remark
        existing.data_status = outcome.data_status
        existing.confidence_score = outcome.confidence_score
        existing.needs_review = outcome.needs_review
        existing.update_time = datetime.now(UTC)
        await session.flush()
        await session.refresh(existing)
        return existing

    async def upsert_placeholder_not_find(
        self,
        session: AsyncSession,
        *,
        result_id: int,
        task_id: int,
        rule: TableExtractionRule,
        remark: str,
    ) -> ExtractedResult:
        return await self.upsert_result(
            session,
            result_id=result_id,
            task_id=task_id,
            rule=rule,
            outcome=ExtractionOutcome(
                data_status="NOT_FIND",
                extraction_route=None,
                table_data=None,
                start_page=None,
                end_page=None,
                bbox=None,
                confidence_score=Decimal("100.00"),
                needs_review="0",
                remark=remark,
            ),
        )

    async def list_pending_review_rows(
        self,
        session: AsyncSession,
        *,
        task_id: int,
    ) -> list[ExtractedResult]:
        statement = (
            select(ExtractedResult)
            .where(
                ExtractedResult.task_id == task_id,
                ExtractedResult.needs_review == "1",
            )
            .order_by(ExtractedResult.id.asc())
        )
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def list_by_task(
        self,
        session: AsyncSession,
        *,
        task_id: int,
    ) -> list[ExtractedResult]:
        statement = (
            select(ExtractedResult)
            .where(ExtractedResult.task_id == task_id)
            .order_by(ExtractedResult.id.asc())
        )
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def apply_fix(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        result_id: int,
        fix_table_data: dict[str, object],
        remark: str | None,
    ) -> ExtractedResult:
        statement = select(ExtractedResult).where(
            ExtractedResult.task_id == task_id,
            ExtractedResult.id == result_id,
        )
        row = (await session.execute(statement)).scalar_one()
        row.fix_table_data = fix_table_data
        row.needs_review = "0"
        row.remark = remark
        row.update_time = datetime.now(UTC)
        await session.flush()
        await session.refresh(row)
        return row

    async def count_pending_review_by_task(
        self,
        session: AsyncSession,
        *,
        task_id: int,
    ) -> int:
        statement = select(func.count()).select_from(ExtractedResult).where(
            ExtractedResult.task_id == task_id,
            ExtractedResult.needs_review == "1",
        )
        return int((await session.execute(statement)).scalar_one())
