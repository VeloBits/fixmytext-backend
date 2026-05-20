"""create operation_history table

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-23 10:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
__all__ = [
    "revision",
    "down_revision",
    "branch_labels",
    "depends_on",
    "upgrade",
    "downgrade",
]


def upgrade() -> None:
    op.create_table(
        "operation_history",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.Column("tool_label", sa.String(200), nullable=False),
        sa.Column("tool_type", sa.String(20), nullable=False),
        sa.Column("input_preview", sa.Text(), nullable=False),
        sa.Column("output_preview", sa.Text(), nullable=False),
        sa.Column("input_length", sa.Integer(), nullable=False),
        sa.Column("output_length", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(20), server_default=sa.text("'success'"), nullable=False
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="activity",
    )
    op.create_index(
        "ix_operation_history_user_id",
        "operation_history",
        ["user_id"],
        schema="activity",
    )
    op.create_index(
        "ix_operation_history_tool_id",
        "operation_history",
        ["tool_id"],
        schema="activity",
    )
    op.create_index(
        "ix_operation_history_created_at",
        "operation_history",
        ["created_at"],
        schema="activity",
    )
    # Composite index for paginated user queries (most common access pattern)
    op.create_index(
        "ix_operation_history_user_created",
        "operation_history",
        ["user_id", "created_at"],
        schema="activity",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operation_history_user_created", "operation_history", schema="activity"
    )
    op.drop_index(
        "ix_operation_history_created_at", "operation_history", schema="activity"
    )
    op.drop_index(
        "ix_operation_history_tool_id", "operation_history", schema="activity"
    )
    op.drop_index(
        "ix_operation_history_user_id", "operation_history", schema="activity"
    )
    op.drop_table("operation_history", schema="activity")
