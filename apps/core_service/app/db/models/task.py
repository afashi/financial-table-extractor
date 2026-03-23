from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.core_service.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Task(Base):
    __tablename__ = "t_task"
    __table_args__ = (
        Index(
            "idx_t_task_hash_size_doc_type",
            "file_hash",
            "file_size",
            "doc_type",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    remark: Mapped[str | None] = mapped_column(String(512), nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
