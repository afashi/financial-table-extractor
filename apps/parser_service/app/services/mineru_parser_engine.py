import asyncio
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.core_service.app.schemas.queue import ParserTaskMessage
from apps.parser_service.app.services.mineru_artifact_normalizer import (
    normalize_mineru_content_list,
)
from apps.parser_service.app.services.parser_engine import ParserEngine, ParserEngineError

CommandRunner = Callable[..., None]


class MinerUParserEngine(ParserEngine):
    def __init__(
        self,
        *,
        temp_dir_root: str | Path | None,
        timeout_seconds: int,
        backend: str | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._temp_dir_root = None if temp_dir_root is None else Path(temp_dir_root)
        self._timeout_seconds = timeout_seconds
        self._backend = backend
        self._command_runner = command_runner or _default_command_runner

    async def parse(
        self,
        *,
        source_pdf: bytes,
        message: ParserTaskMessage,
    ) -> bytes:
        self._ensure_pdf_signature(source_pdf)
        try:
            with TemporaryDirectory(dir=self._temp_dir_root) as workdir:
                workdir_path = Path(workdir)
                input_pdf_path = workdir_path / message.file_name
                output_dir = workdir_path / "mineru-output"
                input_pdf_path.write_bytes(source_pdf)

                try:
                    await asyncio.to_thread(
                        self._command_runner,
                        input_pdf_path=input_pdf_path,
                        output_dir=output_dir,
                        timeout_seconds=self._timeout_seconds,
                        backend=self._backend,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    raise ParserEngineError(
                        "Failed to parse source PDF with MinerU.",
                        reason=exc.__class__.__name__,
                    ) from exc

                try:
                    raw_blocks = json.loads(
                        (output_dir / "content_list.json").read_text(encoding="utf-8")
                    )
                except FileNotFoundError as exc:
                    raise ParserEngineError(
                        "MinerU output did not contain content_list.json.",
                        reason="ContentListMissing",
                    ) from exc
                except (json.JSONDecodeError, OSError) as exc:
                    raise ParserEngineError(
                        "Failed to parse source PDF with MinerU.",
                        reason=exc.__class__.__name__,
                    ) from exc
        except OSError as exc:
            raise ParserEngineError(
                "Failed to parse source PDF with MinerU.",
                reason=exc.__class__.__name__,
            ) from exc

        canonical_blocks = normalize_mineru_content_list(raw_blocks)
        return json.dumps(canonical_blocks, ensure_ascii=True).encode("utf-8")


def _default_command_runner(
    *,
    input_pdf_path: Path,
    output_dir: Path,
    timeout_seconds: int,
    backend: str | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = ["mineru", "-p", str(input_pdf_path), "-o", str(output_dir)]
    if backend:
        command.extend(["-b", backend])

    subprocess.run(
        command,
        check=True,
        timeout=timeout_seconds,
        capture_output=True,
        text=True,
    )
