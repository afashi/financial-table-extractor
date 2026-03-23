import json

from apps.core_service.app.schemas.queue import ParserTaskMessage
from apps.parser_service.app.schemas.artifact import build_placeholder_content_list


class ParserEngineError(Exception):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason or self.__class__.__name__


class ParserEngine:
    async def parse(
        self,
        *,
        source_pdf: bytes,
        message: ParserTaskMessage,
    ) -> bytes:
        raise NotImplementedError


class SkeletonParserEngine(ParserEngine):
    async def parse(
        self,
        *,
        source_pdf: bytes,
        message: ParserTaskMessage,
    ) -> bytes:
        if not source_pdf:
            raise ParserEngineError(
                "Source PDF payload is empty.",
                reason="EmptySourcePdf",
            )

        if not source_pdf.startswith(b"%PDF"):
            raise ParserEngineError(
                "Source file does not look like a PDF document.",
                reason="InvalidPdfSignature",
            )

        content_list = build_placeholder_content_list(message)
        return json.dumps(content_list, ensure_ascii=True).encode("utf-8")
