from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.core_service.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class DocumentToc(Base):
    __tablename__ = "t_document_toc"
    __table_args__ = (Index("idx_t_document_toc_task", "task_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    start_y: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    end_y: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("t_document_toc.id"),
        nullable=True,
    )
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
