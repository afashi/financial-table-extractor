from datetime import UTC, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.core_service.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class TableExtractionRule(Base):
    __tablename__ = "t_table_extraction_rule"
    __table_args__ = (
        Index("idx_t_rule_doc_type_code", "doc_type", "target_table_code", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_table_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    path_fingerprints: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    anchor_rule: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    semantic_anchor_text: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    semantic_vector: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    min_match_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    is_active: Mapped[str] = mapped_column(String(1), nullable=False, default="1")
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
