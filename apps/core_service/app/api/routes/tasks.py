from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from apps.core_service.app.api.dependencies import get_task_service
from apps.core_service.app.schemas.tasks import TaskReadResponse, TaskSubmissionResponse
from apps.core_service.app.services.task_service import TaskService
from apps.shared.enums.doc_type import DocumentType

router = APIRouter(tags=["tasks"])
TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]


@router.post("/api/v1/extract", response_model=TaskSubmissionResponse)
async def create_extract_task(
    response: Response,
    doc_type: Annotated[DocumentType, Form()],
    file: Annotated[UploadFile, File()],
    service: TaskServiceDependency,
) -> TaskSubmissionResponse:
    result = await service.create_extract_task(doc_type=doc_type, upload=file)
    response.status_code = status.HTTP_200_OK if result.deduplicated else status.HTTP_201_CREATED
    return TaskSubmissionResponse.from_record(result.task, deduplicated=result.deduplicated)


@router.get("/tasks/{task_id}", response_model=TaskReadResponse)
async def get_task(
    task_id: int,
    service: TaskServiceDependency,
) -> TaskReadResponse:
    task = await service.get_task(task_id)
    return TaskReadResponse.from_record(task)
