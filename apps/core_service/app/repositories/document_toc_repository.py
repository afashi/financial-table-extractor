from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.db.models.document_toc import DocumentToc
from apps.core_service.app.schemas.toc import TocDraftNode


class DocumentTocRepository:
    async def replace_for_task(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        drafts: list[TocDraftNode],
    ) -> list[DocumentToc]:
        await session.execute(delete(DocumentToc).where(DocumentToc.task_id == task_id))

        rows: list[DocumentToc] = []
        latest_ids_by_level: dict[int, int] = {}
        for draft in drafts:
            row = DocumentToc(
                task_id=task_id,
                level=draft.level,
                title=draft.title,
                start_page=draft.start_page,
                end_page=draft.end_page,
                start_y=draft.start_y,
                end_y=draft.end_y,
                parent_id=latest_ids_by_level.get(draft.level - 1),
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            rows.append(row)
            latest_ids_by_level[draft.level] = row.id

        return rows
