"""add auth.user_ui_settings.sidebar_chips

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-22

Adds the ordered tool-panel chip-row config as a JSONB list column:
[{"type": "view" | "group" | "custom_group", "id": str}, ...].

[] (the default) means "never customized" - the client renders its default
row (All / Pinned / Recent / Suggested). No backfill: every existing user
gets the default row, which replaces the removed USE_CASE_TABS category tabs.

downgrade() drops the column: chip-row customizations are lost (structure-only
restore, same policy as 0003/0004).
"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_SCHEMA = "auth"


def upgrade() -> None:
    op.add_column(
        "user_ui_settings",
        sa.Column(
            "sidebar_chips",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema=AUTH_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("user_ui_settings", "sidebar_chips", schema=AUTH_SCHEMA)
