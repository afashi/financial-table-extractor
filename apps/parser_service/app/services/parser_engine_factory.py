from apps.parser_service.app.services.mineru_parser_engine import MinerUParserEngine
from apps.parser_service.app.services.parser_engine import ParserEngine, SkeletonParserEngine
from apps.parser_service.app.settings import Settings


def build_parser_engine(settings: Settings) -> ParserEngine:
    if settings.parser_backend == "mineru":
        return MinerUParserEngine(
            temp_dir_root=settings.parser_temp_dir,
            timeout_seconds=settings.parser_timeout_seconds,
            backend=settings.mineru_backend,
        )

    return SkeletonParserEngine()
