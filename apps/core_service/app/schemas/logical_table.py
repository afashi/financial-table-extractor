from pydantic import BaseModel, Field


class LogicalTableSegment(BaseModel):
    page_idx: int
    block_index: int
    bbox: list[float]


class LogicalTable(BaseModel):
    logical_table_id: str
    start_page: int
    end_page: int
    header: list[str]
    rows: list[list[str | None]]
    section_path: list[str] = Field(default_factory=list)
    segments: list[LogicalTableSegment] = Field(default_factory=list)
    context_before: list[str] = Field(default_factory=list)
