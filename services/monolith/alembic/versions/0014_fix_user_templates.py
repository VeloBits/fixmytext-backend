"""Add soft delete to activity.user_templates and create partial index.

Revision ID: 0014
Revises: 0013
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_templates",
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema="activity",
    )

    # Partial index: active templates per user ordered by newest first
    op.execute(
        "CREATE INDEX ix_user_templates_user_active "
        "ON activity.user_templates (user_id, created_at DESC) "
        "WHERE is_deleted = FALSE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_templates_user_active")
    op.drop_column("user_templates", "is_deleted", schema="activity")
