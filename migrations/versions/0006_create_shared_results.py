"""create shared_results table (output only, no input_text)

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-24 10:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
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
    # Drop old table if it exists (schema changed — input_text removed)
    op.execute("DROP TABLE IF EXISTS activity.shared_results CASCADE")

    op.create_table(
        "shared_results",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.Column("tool_label", sa.String(200), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="activity",
    )
    op.create_index(
        "ix_shared_results_user_id", "shared_results", ["user_id"], schema="activity"
    )
    op.create_index(
        "ix_shared_results_created_at",
        "shared_results",
        ["created_at"],
        schema="activity",
    )


def downgrade() -> None:
    op.drop_index("ix_shared_results_created_at", "shared_results", schema="activity")
    op.drop_index("ix_shared_results_user_id", "shared_results", schema="activity")
    op.drop_table("shared_results", schema="activity")
