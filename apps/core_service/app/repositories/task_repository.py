from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.db.models.task import Task


class TaskRepository:
    async def get_by_id(self, session: AsyncSession, task_id: int) -> Task | None:
        return await session.get(Task, task_id)

    async def get_by_fingerprint(
        self,
        session: AsyncSession,
        *,
        file_hash: str,
        file_size: int,
        doc_type: str,
    ) -> Task | None:
        statement = select(Task).where(
            Task.file_hash == file_hash,
            Task.file_size == file_size,
            Task.doc_type == doc_type,
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def create(self, session: AsyncSession, task: Task) -> Task:
        session.add(task)
        await session.flush()
        await session.refresh(task)
        return task

    async def touch(self, session: AsyncSession, task: Task) -> Task:
        task.update_time = datetime.now(UTC)
        await session.flush()
        await session.refresh(task)
        return task

    async def set_status(
        self,
        session: AsyncSession,
        task: Task,
        *,
        status: str,
        remark: str | None,
    ) -> Task:
        task.status = status
        task.remark = remark
        task.update_time = datetime.now(UTC)
        await session.flush()
        await session.refresh(task)
        return task
