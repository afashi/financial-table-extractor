import pytest

from apps.core_service.app.schemas.artifact import ArtifactContentBlock, CellValue
from apps.core_service.app.services.logical_table_builder import LogicalTableBuilder

_MISSING = object()


def _table_block(
    *,
    page_idx: int,
    bbox: list[float],
    rows: list[list[CellValue]],
    section_path: object = _MISSING,
) -> ArtifactContentBlock:
    metadata: dict[str, object] = {}
    if section_path is not _MISSING:
        metadata["section_path"] = section_path
    return ArtifactContentBlock(
        type="table",
        page_idx=page_idx,
        bbox=bbox,
        table_body=rows,
        metadata=metadata,
    )


def _text_block(*, page_idx: int, text: str) -> ArtifactContentBlock:
    return ArtifactContentBlock(
        type="text",
        page_idx=page_idx,
        bbox=[0.0, 0.0, 200.0, 20.0],
        text=text,
    )


def test_builder_merges_adjacent_pages_and_drops_repeated_headers() -> None:
    blocks = [
        _text_block(page_idx=0, text="主营业务收入"),
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 180.0],
            rows=[["分部", "收入"], ["境内", "100"], ["境外", "80"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
        _text_block(page_idx=1, text="续表：主营业务收入"),
        _table_block(
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 140.0],
            rows=[["分部", "收入"], ["其他", "20"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 1
    assert tables[0].start_page == 0
    assert tables[0].end_page == 1
    assert tables[0].header == ["分部", "收入"]
    assert tables[0].rows == [["境内", "100"], ["境外", "80"], ["其他", "20"]]
    assert [segment.page_idx for segment in tables[0].segments] == [0, 1]
    assert tables[0].context_before == ["主营业务收入"]


def test_builder_merges_adjacent_pages_when_header_and_section_match() -> None:
    blocks = [
        _text_block(page_idx=0, text="主营业务收入"),
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 180.0],
            rows=[["分部", "收入"], ["境内", "100"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
        _table_block(
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 140.0],
            rows=[["分部", "收入"], ["境外", "80"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 1
    assert tables[0].rows == [["境内", "100"], ["境外", "80"]]
    assert [segment.page_idx for segment in tables[0].segments] == [0, 1]


def test_builder_keeps_distinct_tables_separate_when_section_changes() -> None:
    blocks = [
        _text_block(page_idx=0, text="按地区分类"),
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 160.0],
            rows=[["分部", "收入"], ["境内", "100"]],
            section_path=["管理层讨论与分析", "地区结构"],
        ),
        _text_block(page_idx=1, text="按产品分类"),
        _table_block(
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 160.0],
            rows=[["分部", "收入"], ["产品A", "100"]],
            section_path=["管理层讨论与分析", "产品结构"],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 2
    assert tables[0].rows == [["境内", "100"]]
    assert tables[1].rows == [["产品A", "100"]]


def test_builder_preserves_section_path_for_routing() -> None:
    blocks = [
        _text_block(page_idx=0, text="主营业务收入"),
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 180.0],
            rows=[["分部", "收入"], ["境内", "100"]],
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 1
    assert tables[0].section_path == ["管理层讨论与分析", "主营业务分析"]


def test_builder_does_not_merge_without_valid_section_path_or_continuation_text() -> None:
    blocks = [
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 160.0],
            rows=[["分部", "收入"], ["境内", "100"]],
        ),
        _table_block(
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 160.0],
            rows=[["分部", "收入"], ["境外", "80"]],
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 2
    assert tables[0].rows == [["境内", "100"]]
    assert tables[1].rows == [["境外", "80"]]


@pytest.mark.parametrize("section_path", [[], [""], ["  "]])
def test_builder_does_not_merge_with_empty_or_blank_section_path(
    section_path: list[str],
) -> None:
    blocks = [
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 160.0],
            rows=[["分部", "收入"], ["境内", "100"]],
            section_path=section_path,
        ),
        _table_block(
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 160.0],
            rows=[["分部", "收入"], ["境外", "80"]],
            section_path=section_path,
        ),
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 2
    assert tables[0].rows == [["境内", "100"]]
    assert tables[1].rows == [["境外", "80"]]


def test_builder_normalizes_rows_preserving_none_and_stringifying_numbers() -> None:
    blocks = [
        _table_block(
            page_idx=0,
            bbox=[0.0, 40.0, 300.0, 180.0],
            rows=[
                ["列1", "列2", "列3"],
                [None, 1, 2.5],
                [" ", None, "\n"],
                [None, None, None],
                [" 文本 ", 3, 4.0],
            ],
            section_path=["管理层讨论与分析", "数据明细"],
        )
    ]

    tables = LogicalTableBuilder().build(blocks)

    assert len(tables) == 1
    assert tables[0].rows == [
        [None, "1", "2.5"],
        ["文本", "3", "4.0"],
    ]
