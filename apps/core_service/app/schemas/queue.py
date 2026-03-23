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
