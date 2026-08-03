"""add auth.user_preferences.auto_run

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03

Manual execution ("Run") became the default tool-execution mode; the previous
debounce-driven auto-run is now an opt-in preference. false (the default, and
what every existing row is backfilled to by the server_default) means the user
must press Run - deliberately NOT preserving the old auto-run behavior for
existing users, since the whole point of the change is to stop idle keystrokes
from consuming quota.

downgrade() drops the column: the opt-in choice is lost and every user falls
back to the client's default (manual) mode. Structure-only restore, same policy
as 0003/0004/0005.
"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_SCHEMA = "auth"


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column(
            "auto_run",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=AUTH_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "auto_run", schema=AUTH_SCHEMA)
