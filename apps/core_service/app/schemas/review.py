from datetime import datetime

from pydantic import BaseModel


class ReviewQueueItem(BaseModel):
    task_id: str
    doc_type: str
    file_name: str
    update_time: datetime
    pending_result_count: int
    target_table_codes: list[str]


class ExtractedResultRead(BaseModel):
    result_id: str
    target_table_code: str
    data_status: str
    extraction_route: str | None = None
    confidence_score: str
    needs_review: str
    table_data: dict[str, object] | None = None
    fix_table_data: dict[str, object] | None = None
    remark: str | None = None


class ResultFixRequest(BaseModel):
    fix_table_data: dict[str, object]
    remark: str | None = None
