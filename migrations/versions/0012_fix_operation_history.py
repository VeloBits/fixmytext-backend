"""Add soft delete to operation_history, add CHECK constraints and partial indexes.

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add soft delete column
    op.add_column(
        "operation_history",
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema="activity",
    )

    # Add CHECK constraint on tool_type
    op.create_check_constraint(
        "ck_op_history_tool_type",
        "operation_history",
        "tool_type IN ('api', 'ai', 'local', 'select', 'action', 'drawer')",
        schema="activity",
    )

    # Add CHECK constraint on status
    op.create_check_constraint(
        "ck_op_history_status",
        "operation_history",
        "status IN ('success', 'error')",
        schema="activity",
    )

    # Partial index: paginated history for a user (most common query pattern)
    op.execute(
        "CREATE INDEX ix_op_history_user_date "
        "ON activity.operation_history (user_id, created_at DESC) "
        "WHERE is_deleted = FALSE"
    )

    # Partial index: history filtered by tool
    op.execute(
        "CREATE INDEX ix_op_history_user_tool_date "
        "ON activity.operation_history (user_id, tool_id, created_at DESC) "
        "WHERE is_deleted = FALSE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_op_history_user_tool_date")
    op.execute("DROP INDEX IF EXISTS ix_op_history_user_date")
    op.drop_constraint(
        "ck_op_history_status", "operation_history", schema="activity", type_="check"
    )
    op.drop_constraint(
        "ck_op_history_tool_type", "operation_history", schema="activity", type_="check"
    )
    op.drop_column("operation_history", "is_deleted", schema="activity")
