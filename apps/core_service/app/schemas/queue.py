from pydantic import BaseModel

from apps.shared.enums.doc_type import DocumentType


class ParserTaskMessage(BaseModel):
    task_id: str
    doc_type: DocumentType
    file_name: str
    file_hash: str
    file_size: int
    bucket: str
    source_object_key: str


class ExtractorTaskMessage(BaseModel):
    task_id: str
    doc_type: DocumentType
    bucket: str
    content_list_object_key: str
    target_table_codes: list[str] | None = None
