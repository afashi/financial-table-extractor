from typing import Annotated

from fastapi import APIRouter, Depends

from apps.core_service.app.api.dependencies import get_review_service
from apps.core_service.app.schemas.review import (
    ExtractedResultRead,
    ResultFixRequest,
    ReviewQueueItem,
)
from apps.core_service.app.services.review_service import ReviewService

router = APIRouter(tags=["review"])
ReviewServiceDependency = Annotated[ReviewService, Depends(get_review_service)]


@router.get("/api/v1/review/tasks", response_model=list[ReviewQueueItem])
async def list_review_tasks(
    service: ReviewServiceDependency,
) -> list[ReviewQueueItem]:
    return await service.list_pending_review_tasks()


@router.get("/api/v1/tasks/{task_id}/results", response_model=list[ExtractedResultRead])
async def get_task_results(
    task_id: int,
    service: ReviewServiceDependency,
) -> list[ExtractedResultRead]:
    return await service.get_task_results(task_id=task_id)


@router.patch("/api/v1/tasks/{task_id}/results/{result_id}", response_model=ExtractedResultRead)
async def patch_result_fix(
    task_id: int,
    result_id: int,
    request: ResultFixRequest,
    service: ReviewServiceDependency,
) -> ExtractedResultRead:
    return await service.apply_fix(
        task_id=task_id,
        result_id=result_id,
        fix_table_data=request.fix_table_data,
        remark=request.remark,
    )
