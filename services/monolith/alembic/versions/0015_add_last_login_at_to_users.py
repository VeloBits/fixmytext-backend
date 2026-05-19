"""add last_login_at to users

Revision ID: 0015
Revises: 0014
Create Date: 2026-03-26 09:06:24.540953

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: Union[str, None] = "0014"
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
    op.add_column(
        "users",
        sa.Column("last_login_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_column("users", "last_login_at", schema="auth")
