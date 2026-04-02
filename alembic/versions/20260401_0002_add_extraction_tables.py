"""add extraction tables"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260401_0002"
down_revision: str | None = "20260323_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "t_table_extraction_rule",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("target_table_code", sa.String(length=64), nullable=False),
        sa.Column("target_table_name", sa.String(length=128), nullable=False),
        sa.Column(
            "path_fingerprints",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("anchor_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("semantic_anchor_text", sa.String(length=2000), nullable=True),
        sa.Column("min_match_score", sa.Numeric(4, 3), nullable=True),
        sa.Column(
            "is_active",
            sa.String(length=1),
            nullable=False,
            server_default=sa.text("'1'"),
        ),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "update_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_t_rule_doc_type_code",
        "t_table_extraction_rule",
        ["doc_type", "target_table_code"],
        unique=True,
    )

    op.create_table(
        "t_extracted_result",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("target_table_code", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("extraction_route", sa.String(length=32), nullable=True),
        sa.Column("data_status", sa.String(length=32), nullable=False),
        sa.Column("table_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fix_table_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("start_page", sa.Integer(), nullable=True),
        sa.Column("end_page", sa.Integer(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "needs_review",
            sa.String(length=1),
            nullable=False,
            server_default=sa.text("'0'"),
        ),
        sa.Column("remark", sa.String(length=512), nullable=True),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "update_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["t_table_extraction_rule.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_t_result_task", "t_extracted_result", ["task_id"], unique=False)
    op.create_index("idx_t_result_review", "t_extracted_result", ["needs_review"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_t_result_review", table_name="t_extracted_result")
    op.drop_index("idx_t_result_task", table_name="t_extracted_result")
    op.drop_table("t_extracted_result")
    op.drop_index("idx_t_rule_doc_type_code", table_name="t_table_extraction_rule")
    op.drop_table("t_table_extraction_rule")
