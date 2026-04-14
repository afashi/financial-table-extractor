"""add document toc and rule vectors"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "20260413_0003"
down_revision: str | None = "20260401_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "t_document_toc",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("start_y", sa.Numeric(10, 4), nullable=True),
        sa.Column("end_y", sa.Numeric(10, 4), nullable=True),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
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
        sa.ForeignKeyConstraint(["parent_id"], ["t_document_toc.id"]),
    )
    op.create_index("idx_t_document_toc_task", "t_document_toc", ["task_id"], unique=False)
    op.add_column(
        "t_table_extraction_rule",
        sa.Column("semantic_vector", Vector(1024), nullable=True),
    )
    op.create_index(
        "idx_t_rule_vector",
        "t_table_extraction_rule",
        ["semantic_vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"semantic_vector": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("idx_t_rule_vector", table_name="t_table_extraction_rule")
    op.drop_column("t_table_extraction_rule", "semantic_vector")
    op.drop_index("idx_t_document_toc_task", table_name="t_document_toc")
    op.drop_table("t_document_toc")
