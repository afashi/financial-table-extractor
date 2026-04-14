from pydantic import BaseModel


class TocDraftNode(BaseModel):
    title: str
    level: int
    start_page: int
    end_page: int
    start_y: float | None = None
    end_y: float | None = None
    parent_title: str | None = None
