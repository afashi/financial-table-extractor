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
    assert blocks[0]["span_count"] == 3

    assert blocks[2]["type"] == "table"
    assert blocks[2]["table_body"] == [["分部", "营业收入"], ["境内", "100"]]
    assert blocks[2]["metadata"]["section_path"] == ["管理层讨论与分析", "主营业务分析"]
    assert blocks[2]["img_path"] == "tables/page-0-table-0.png"
