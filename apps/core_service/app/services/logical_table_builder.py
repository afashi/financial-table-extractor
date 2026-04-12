from apps.core_service.app.schemas.artifact import ArtifactContentBlock, CellValue
from apps.core_service.app.schemas.logical_table import LogicalTable, LogicalTableSegment


class LogicalTableBuilder:
    def build(self, blocks: list[ArtifactContentBlock]) -> list[LogicalTable]:
        logical_tables: list[LogicalTable] = []
        active_table: LogicalTable | None = None
        active_header: list[str] | None = None
        active_block: ArtifactContentBlock | None = None

        for index, block in enumerate(blocks):
            if block.type != "table" or not block.table_body:
                continue

            header = self._normalize_header(block.table_body[0])
            rows = self._normalize_rows(block.table_body[1:])
            if active_table is None:
                active_table = self._new_logical_table(blocks, index, block, header, rows)
                active_header = header
                active_block = block
                continue

            if (
                active_header is not None
                and active_block is not None
                and self._should_merge(
                    previous_block=active_block,
                    next_block=block,
                    previous_header=active_header,
                    next_index=index,
                    blocks=blocks,
                )
            ):
                active_table.end_page = block.page_idx
                active_table.segments.append(
                    LogicalTableSegment(
                        page_idx=block.page_idx,
                        block_index=index,
                        bbox=block.bbox,
                    )
                )
                active_table.rows.extend(
                    self._normalize_rows(
                        self._drop_repeated_header(block.table_body, active_header)
                    )
                )
                active_block = block
                continue

            logical_tables.append(active_table)
            active_table = self._new_logical_table(blocks, index, block, header, rows)
            active_header = header
            active_block = block

        if active_table is not None:
            logical_tables.append(active_table)

        return logical_tables

    def _new_logical_table(
        self,
        blocks: list[ArtifactContentBlock],
        index: int,
        block: ArtifactContentBlock,
        header: list[str],
        rows: list[list[str | None]],
    ) -> LogicalTable:
        return LogicalTable(
            logical_table_id=f"logical-table-{block.page_idx}-{index}",
            start_page=block.page_idx,
            end_page=block.page_idx,
            header=header,
            rows=rows,
            section_path=list(self._section_path(block) or ()),
            segments=[
                LogicalTableSegment(
                    page_idx=block.page_idx,
                    block_index=index,
                    bbox=block.bbox,
                )
            ],
            context_before=self._collect_preceding_texts(blocks, index),
        )

    def _should_merge(
        self,
        *,
        previous_block: ArtifactContentBlock,
        next_block: ArtifactContentBlock,
        previous_header: list[str],
        next_index: int,
        blocks: list[ArtifactContentBlock],
    ) -> bool:
        if next_block.page_idx != previous_block.page_idx + 1:
            return False
        if self._normalize_header(next_block.table_body[0]) != previous_header:
            return False

        if any("续表" in text for text in self._collect_preceding_texts(blocks, next_index)):
            return True

        previous_section_path = self._section_path(previous_block)
        next_section_path = self._section_path(next_block)
        return (
            previous_section_path is not None
            and next_section_path is not None
            and previous_section_path == next_section_path
        )

    def _collect_preceding_texts(
        self,
        blocks: list[ArtifactContentBlock],
        index: int,
        *,
        limit: int = 2,
    ) -> list[str]:
        texts: list[str] = []
        cursor = index - 1
        while cursor >= 0 and len(texts) < limit:
            block = blocks[cursor]
            cursor -= 1
            if block.type != "text" or block.text is None:
                continue
            normalized = block.text.strip()
            if normalized:
                texts.append(normalized)
        texts.reverse()
        return texts

    def _drop_repeated_header(
        self,
        rows: list[list[CellValue]],
        previous_header: list[str],
    ) -> list[list[CellValue]]:
        if rows and self._normalize_header(rows[0]) == previous_header:
            return rows[1:]
        return rows

    def _normalize_rows(self, rows: list[list[CellValue]]) -> list[list[str | None]]:
        normalized_rows: list[list[str | None]] = []
        for row in rows:
            normalized = self._normalize_row(row)
            if any(cell not in (None, "") for cell in normalized):
                normalized_rows.append(normalized)
        return normalized_rows

    def _normalize_header(self, row: list[CellValue]) -> list[str]:
        return [cell if cell is not None else "" for cell in self._normalize_row(row)]

    def _normalize_row(self, row: list[CellValue]) -> list[str | None]:
        normalized: list[str | None] = []
        for cell in row:
            if cell is None:
                normalized.append(None)
                continue
            text = str(cell).replace("\n", " ").strip()
            normalized.append(text)
        return normalized

    def _section_path(self, block: ArtifactContentBlock) -> tuple[str, ...] | None:
        value = block.metadata.get("section_path")
        if not isinstance(value, list) or not value:
            return None
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                return None
            text = item.strip()
            if not text:
                return None
            normalized.append(text)
        return tuple(normalized)
