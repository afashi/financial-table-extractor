from pydantic import BaseModel, Field
from starlette import status

from apps.core_service.app.errors import AppError
from apps.core_service.app.schemas.queue import ExtractorTaskMessage
from apps.core_service.app.utils.object_storage import build_content_list_object_key


class RetriggerRequest(BaseModel):
    task_id: str
    target_table_codes: list[str] = Field(min_length=1)


class RetriggerResponse(BaseModel):
    task_id: str
    accepted: bool
    target_table_codes: list[str]


class RetriggerService:
    def __init__(self, *, session, task_repository, queue_client, bucket_name: str) -> None:
        self._session = session
        self._task_repository = task_repository
        self._queue_client = queue_client
        self._bucket_name = bucket_name

    async def retrigger(
        self,
        *,
        task_id: int,
        target_table_codes: list[str],
    ) -> RetriggerResponse:
        task = await self._task_repository.get_by_id(self._session, task_id)
        if task is None:
            raise AppError(
                code="TASK_NOT_FOUND",
                message=f"Task {task_id} was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                task_id=task_id,
            )

        message = ExtractorTaskMessage(
            task_id=str(task.id),
            doc_type=task.doc_type,
            bucket=self._bucket_name,
            content_list_object_key=build_content_list_object_key(task.id),
            target_table_codes=target_table_codes,
        )
        await self._queue_client.publish_reextract_task(message)
        return RetriggerResponse(
            task_id=str(task.id),
            accepted=True,
            target_table_codes=target_table_codes,
        )
