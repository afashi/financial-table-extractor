from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


CellValue = str | int | float | None


class ArtifactContentBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    page_idx: int
    bbox: list[float]
    text: str | None = None
    table_body: list[list[CellValue]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def extra_fields(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


ARTIFACT_BLOCKS_ADAPTER = TypeAdapter(list[ArtifactContentBlock])


def load_content_list(payload: bytes) -> list[ArtifactContentBlock]:
    return ARTIFACT_BLOCKS_ADAPTER.validate_json(payload)
