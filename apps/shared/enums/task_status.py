from enum import StrEnum


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
