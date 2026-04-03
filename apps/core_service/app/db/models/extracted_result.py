from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.core_service.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExtractedResult(Base):
    __tablename__ = "t_extracted_result"
    __table_args__ = (
        Index("idx_t_result_task", "task_id"),
        Index("idx_t_result_review", "needs_review"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("t_table_extraction_rule.id"),
        nullable=False,
    )
    target_table_code: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    extraction_route: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_status: Mapped[str] = mapped_column(String(32), nullable=False)
    table_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    fix_table_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    start_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict[str, object] | list[object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    needs_review: Mapped[str] = mapped_column(String(1), nullable=False, default="0")
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
