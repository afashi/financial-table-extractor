import hashlib
from dataclasses import dataclass

from fastapi import status

from apps.core_service.app.errors import AppError


@dataclass(slots=True)
class FileFingerprint:
    file_name: str
    file_hash: str
    file_size: int


def build_file_fingerprint(file_name: str, file_bytes: bytes) -> FileFingerprint:
    if not file_name:
        raise AppError(
            code="INVALID_FILE_UPLOAD",
            message="Uploaded file must include a filename.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not file_bytes:
        raise AppError(
            code="INVALID_FILE_UPLOAD",
            message="Uploaded file cannot be empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return FileFingerprint(
        file_name=file_name,
        file_hash=hashlib.sha256(file_bytes).hexdigest(),
        file_size=len(file_bytes),
    )
