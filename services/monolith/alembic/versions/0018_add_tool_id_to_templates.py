"""Add tool_id column to user_templates.

Templates now remember which tool they were saved from so they can be
reopened in the correct tool context.

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-01
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_templates",
        sa.Column("tool_id", sa.String(100), nullable=True),
        schema="activity",
    )


def downgrade() -> None:
    op.drop_column("user_templates", "tool_id", schema="activity")
