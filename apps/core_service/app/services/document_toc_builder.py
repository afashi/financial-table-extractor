from apps.core_service.app.schemas.artifact import ArtifactContentBlock
from apps.core_service.app.schemas.toc import TocDraftNode


class DocumentTocBuilder:
    def build(
        self,
        *,
        task_id: int,
        blocks: list[ArtifactContentBlock],
    ) -> list[TocDraftNode]:
        del task_id
        nodes_by_path: dict[tuple[str, ...], TocDraftNode] = {}

        for block in blocks:
            path = self._path_for_block(block)
            if not path:
                continue

            for depth in range(1, len(path) + 1):
                current_path = tuple(path[:depth])
                node = nodes_by_path.get(current_path)
                page_idx = block.page_idx
                y0 = float(block.bbox[1]) if len(block.bbox) > 1 else None
                y1 = float(block.bbox[3]) if len(block.bbox) > 3 else None

                if node is None:
                    nodes_by_path[current_path] = TocDraftNode(
                        title=current_path[-1],
                        level=depth,
                        start_page=page_idx,
                        end_page=page_idx,
                        start_y=y0,
                        end_y=y1,
                        parent_title=current_path[-2] if depth > 1 else None,
                    )
                    continue

                node.end_page = page_idx
                node.end_y = y1

        return list(nodes_by_path.values())

    def _path_for_block(self, block: ArtifactContentBlock) -> list[str]:
        raw_path = block.metadata.get("section_path")
        if isinstance(raw_path, list) and raw_path:
            return [str(item).strip() for item in raw_path if str(item).strip()]
        return []
