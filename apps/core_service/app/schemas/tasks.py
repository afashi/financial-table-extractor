from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.core_service.app.db.models.task import Task
from apps.shared.enums.doc_type import DocumentType
from apps.shared.enums.task_status import TaskStatus


class TaskReadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    doc_type: DocumentType
    file_name: str
    file_hash: str
    file_size: int
    status: TaskStatus
    remark: str | None = None
    create_time: datetime
    update_time: datetime

    @classmethod
    def from_record(cls, task: Task) -> "TaskReadResponse":
        return cls(
            task_id=str(task.id),
            doc_type=DocumentType(task.doc_type),
            file_name=task.file_name,
            file_hash=task.file_hash,
            file_size=task.file_size,
            status=TaskStatus(task.status),
            remark=task.remark,
            create_time=task.create_time,
            update_time=task.update_time,
        )


class TaskSubmissionResponse(TaskReadResponse):
    deduplicated: bool = Field(
        description="True when an existing task matched the upload fingerprint.",
    )

    @classmethod
    def from_record(
        cls,
        task: Task,
        *,
        deduplicated: bool,
    ) -> "TaskSubmissionResponse":
        base = TaskReadResponse.from_record(task).model_dump()
        return cls(**base, deduplicated=deduplicated)
