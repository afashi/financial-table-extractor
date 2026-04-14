from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.services.document_toc_builder import DocumentTocBuilder


def _text_block(
    *,
    page_idx: int,
    y0: float,
    text: str,
    section_path: list[str],
    block_role: str = "heading",
) -> ArtifactContentBlock:
    return ArtifactContentBlock(
        type="text",
        page_idx=page_idx,
        bbox=[0.0, y0, 200.0, y0 + 20.0],
        text=text,
        metadata={
            "section_path": section_path,
            "block_role": block_role,
        },
    )


def test_document_toc_builder_creates_tree_and_page_ranges() -> None:
    blocks = [
        _text_block(page_idx=0, y0=0.0, text="管理层讨论与分析", section_path=["管理层讨论与分析"]),
        _text_block(
            page_idx=0,
            y0=24.0,
            text="主营业务分析",
            section_path=["管理层讨论与分析", "主营业务分析"],
        ),
        ArtifactContentBlock(
            type="table",
            page_idx=1,
            bbox=[0.0, 40.0, 300.0, 180.0],
            metadata={"section_path": ["管理层讨论与分析", "主营业务分析"]},
            table_body=[["分部", "收入"], ["境内", "100"]],
        ),
    ]

    nodes = DocumentTocBuilder().build(task_id=1001, blocks=blocks)

    assert [node.title for node in nodes] == ["管理层讨论与分析", "主营业务分析"]
    assert nodes[0].level == 1
    assert nodes[0].parent_title is None
    assert nodes[0].start_page == 0
    assert nodes[0].end_page == 1
    assert nodes[1].level == 2
    assert nodes[1].parent_title == "管理层讨论与分析"
    assert nodes[1].start_page == 0
    assert nodes[1].end_page == 1
