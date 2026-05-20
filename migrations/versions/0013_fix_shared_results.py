"""Add input_text, view_count, expires_at to activity.shared_results.

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add input_text (nullable — existing rows have no input)
    op.add_column(
        "shared_results",
        sa.Column("input_text", sa.Text(), nullable=True),
        schema="activity",
    )

    # Add view_count
    op.add_column(
        "shared_results",
        sa.Column(
            "view_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        schema="activity",
    )

    # Add expires_at as a proper TIMESTAMPTZ column
    op.add_column(
        "shared_results",
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
        schema="activity",
    )

    # Backfill expires_at for existing rows: created_at + 30 days
    op.execute("""
        UPDATE activity.shared_results
        SET expires_at = created_at + INTERVAL '30 days'
        WHERE expires_at IS NULL
    """)

    # Make expires_at NOT NULL now that all rows are backfilled
    op.alter_column("shared_results", "expires_at", nullable=False, schema="activity")

    # Index for background cleanup job (find expired shares)
    op.create_index(
        "ix_shared_results_expires_at",
        "shared_results",
        ["expires_at"],
        schema="activity",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shared_results_expires_at", table_name="shared_results", schema="activity"
    )
    op.drop_column("shared_results", "expires_at", schema="activity")
    op.drop_column("shared_results", "view_count", schema="activity")
    op.drop_column("shared_results", "input_text", schema="activity")
