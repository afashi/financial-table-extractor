import json

import pytest
from pydantic import ValidationError

from apps.core_service.app.schemas.artifact import load_content_list


def test_load_content_list_preserves_table_blocks_and_extra_fields() -> None:
    payload = json.dumps(
        [
            {
                "type": "text",
                "page_idx": 0,
                "bbox": [0.0, 0.0, 200.0, 24.0],
                "text": "管理层讨论与分析",
            },
            {
                "type": "table",
                "page_idx": 0,
                "bbox": [10.0, 40.0, 300.0, 180.0],
                "table_body": [["分部", "收入"], ["境内", "100"]],
                "metadata": {"section_path": ["管理层讨论与分析", "主营业务分析"]},
                "table_caption": "主营业务收入表",
            },
        ],
        ensure_ascii=True,
    ).encode("utf-8")

    blocks = load_content_list(payload)

    assert [block.type for block in blocks] == ["text", "table"]
    assert blocks[0].text == "管理层讨论与分析"
    assert blocks[1].table_body == [["分部", "收入"], ["境内", "100"]]
    assert blocks[1].metadata["section_path"] == ["管理层讨论与分析", "主营业务分析"]
    assert blocks[1].extra_fields["table_caption"] == "主营业务收入表"


def test_load_content_list_rejects_non_array_payload() -> None:
    with pytest.raises(ValidationError):
        load_content_list(b'{"type":"table","page_idx":0,"bbox":[0,0,1,1]}')
