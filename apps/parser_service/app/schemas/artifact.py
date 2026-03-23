from datetime import UTC, datetime

from pydantic import BaseModel, Field

from apps.core_service.app.schemas.queue import ParserTaskMessage


class ContentBlock(BaseModel):
    type: str
    page_idx: int
    bbox: list[float]
    text: str | None = None
    metadata: dict[str, str | int] = Field(default_factory=dict)


def build_placeholder_content_list(message: ParserTaskMessage) -> list[dict[str, object]]:
    block = ContentBlock(
        type="text",
        page_idx=0,
        bbox=[0.0, 0.0, 0.0, 0.0],
        text=f"Parser skeleton placeholder for {message.file_name}",
        metadata={
            "generated_at": datetime.now(UTC).isoformat(),
            "task_id": message.task_id,
            "doc_type": message.doc_type,
            "source_object_key": message.source_object_key,
        },
    )
    return [block.model_dump(mode="json")]
