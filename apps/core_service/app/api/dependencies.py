from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core_service.app.services.task_service import TaskService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.database_client.session_factory
    async with session_factory() as session:
        yield session


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_task_service(
    request: Request,
    session: SessionDependency,
) -> TaskService:
    logger = request.app.state.logger
    return TaskService(
        session=session,
        id_generator=request.app.state.task_id_generator,
        logger=logger,
        object_storage_client=request.app.state.object_storage_client,
        queue_client=request.app.state.queue_client,
        trace_id=request.state.trace_id,
    )
