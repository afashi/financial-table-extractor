"""create t_task"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260323_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "t_task",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'QUEUED'"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_t_task_hash_size_doc_type",
        "t_task",
        ["file_hash", "file_size", "doc_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_t_task_hash_size_doc_type", table_name="t_task")
    op.drop_table("t_task")
