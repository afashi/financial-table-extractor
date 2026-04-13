from collections.abc import Sequence
from typing import Any


def normalize_mineru_content_list(raw_blocks: Sequence[dict[str, Any]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []

    for raw in raw_blocks:
        block_type = str(raw.get("type", "")).strip().lower()
        if block_type not in {"text", "table"}:
            continue

        item: dict[str, object] = {
            "type": block_type,
            "page_idx": int(raw.get("page_idx", 0)),
            "bbox": _normalize_bbox(raw.get("bbox")),
            "metadata": _build_metadata(raw),
        }

        if block_type == "text":
            item["text"] = str(raw.get("text", "")).strip()
        else:
            item["table_body"] = _normalize_table_body(raw.get("table_body"))

        for key, value in raw.items():
            if key in {
                "type",
                "page_idx",
                "bbox",
                "text",
                "table_body",
                "section_path",
                "metadata",
                "block_role",
            }:
                continue
            item[key] = value

        normalized.append(item)

    return normalized


def _build_metadata(raw: dict[str, Any]) -> dict[str, object]:
    metadata = dict(raw.get("metadata") or {})

    raw_path = raw.get("section_path", [])
    section_path = [str(item).strip() for item in raw_path if str(item).strip()]
    if section_path:
        metadata["section_path"] = section_path

    block_role = raw.get("block_role")
    if isinstance(block_role, str) and block_role.strip():
        metadata["block_role"] = block_role.strip()

    return metadata


def _normalize_table_body(value: object) -> list[list[str | None]]:
    if not isinstance(value, list):
        return []

    rows: list[list[str | None]] = []
    for row in value:
        if not isinstance(row, list):
            continue
        rows.append([None if cell is None else str(cell) for cell in row])
    return rows


def _normalize_bbox(value: object) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return [0.0, 0.0, 0.0, 0.0]

    normalized: list[float] = []
    for item in list(value)[:4]:
        try:
            normalized.append(float(item))
        except (TypeError, ValueError):
            normalized.append(0.0)

    while len(normalized) < 4:
        normalized.append(0.0)

    return normalized
