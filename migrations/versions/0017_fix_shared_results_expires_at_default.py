"""Add server default to shared_results.expires_at column.

Migration 0013 added the expires_at column and backfilled it but
forgot to set a server_default, causing new INSERTs to fail with a
NOT NULL violation.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-01
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "shared_results",
        "expires_at",
        server_default=sa.text("now() + INTERVAL '30 days'"),
        schema="activity",
    )


def downgrade() -> None:
    op.alter_column(
        "shared_results",
        "expires_at",
        server_default=None,
        schema="activity",
    )
