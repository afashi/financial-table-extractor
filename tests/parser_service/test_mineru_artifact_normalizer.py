import json
from pathlib import Path

from apps.parser_service.app.services.mineru_artifact_normalizer import (
    normalize_mineru_content_list,
)


def test_normalizer_converts_raw_mineru_blocks_to_canonical_contract() -> None:
    raw_blocks = json.loads(
        Path("tests/fixtures/mineru/sample_content_list.json").read_text(encoding="utf-8")
    )

    blocks = normalize_mineru_content_list(raw_blocks)

    assert blocks[0]["type"] == "text"
    assert blocks[0]["page_idx"] == 0
    assert blocks[0]["bbox"] == [0.0, 0.0, 120.0, 20.0]
    assert blocks[0]["text"] == "管理层讨论与分析"
    assert blocks[0]["metadata"]["section_path"] == ["管理层讨论与分析"]
    assert blocks[0]["metadata"]["block_role"] == "heading"
    assert "block_role" not in blocks[0]
    assert blocks[0]["span_count"] == 3

    assert blocks[2]["type"] == "table"
    assert blocks[2]["table_body"] == [["分部", "营业收入"], ["境内", "100"]]
    assert blocks[2]["metadata"]["section_path"] == ["管理层讨论与分析", "主营业务分析"]
    assert blocks[2]["img_path"] == "tables/page-0-table-0.png"


def test_normalizer_filters_non_text_and_non_table_blocks() -> None:
    raw_blocks = [
        {"type": "text", "page_idx": 0, "bbox": [0, 0, 10, 10], "text": "x"},
        {"type": "image", "page_idx": 0, "bbox": [0, 0, 10, 10], "img_path": "a.png"},
        {"type": "TABLE", "page_idx": 1, "bbox": [1, 2, 3, 4], "table_body": [["h"]]},
        {"type": None, "page_idx": 2, "bbox": [1, 2, 3, 4]},
    ]

    blocks = normalize_mineru_content_list(raw_blocks)

    assert [item["type"] for item in blocks] == ["text", "table"]


def test_normalizer_normalizes_table_cells_to_str_or_none() -> None:
    raw_blocks = [
        {
            "type": "table",
            "page_idx": 0,
            "bbox": [0, 0, 10, 10],
            "table_body": [[1, 2.5, True, None], ["x", None, {"a": 1}]],
        }
    ]

    blocks = normalize_mineru_content_list(raw_blocks)

    assert blocks[0]["table_body"] == [["1", "2.5", "True", None], ["x", None, "{'a': 1}"]]


def test_normalizer_canonicalizes_bbox_to_exactly_four_floats() -> None:
    raw_blocks = [
        {"type": "text", "page_idx": 0, "bbox": [1, "2.5", 3, 4, 5], "text": "a"},
        {"type": "table", "page_idx": 0, "bbox": [9], "table_body": [["h"]]},
    ]

    blocks = normalize_mineru_content_list(raw_blocks)

    assert blocks[0]["bbox"] == [1.0, 2.5, 3.0, 4.0]
    assert blocks[1]["bbox"] == [9.0, 0.0, 0.0, 0.0]
