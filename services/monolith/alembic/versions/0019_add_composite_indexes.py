"""Add composite indexes for critical query paths.

These indexes optimize the most frequent queries:
- Pass lookup by user + active status + expiry
- Credit lookup by user + remaining balance
- History pagination by user + timestamp (excluding soft-deleted rows)

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-09
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# Alembic reads these module-level variables by convention
revision: str = "0019"  # noqa: F841
down_revision: Union[str, None] = "0018"  # noqa: F841
branch_labels: Union[str, Sequence[str], None] = None  # noqa: F841
depends_on: Union[str, Sequence[str], None] = None  # noqa: F841


def upgrade() -> None:
    """Add composite indexes for query optimization.

    Each index targets a hot query path identified via slow-query logs:

    1. ``ix_user_passes_active_lookup`` -- speeds up ``check_passes()`` which
       filters ``user_id + is_active + expires_at``.
    2. ``ix_user_credits_active_lookup`` -- speeds up ``_check_credits()``
       which filters ``user_id + credits_remaining > 0``.
    3. ``ix_operation_history_user_created`` -- speeds up the paginated
       history listing that orders by ``created_at DESC`` and excludes
       soft-deleted rows.

    Uses IF NOT EXISTS to make the migration idempotent.
    """
    # Passes: check_passes() filters user_id + is_active + expires_at
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_passes_active_lookup "
        "ON billing.user_passes (user_id, expires_at) "
        "WHERE is_active = true"
    )

    # Credits: _check_credits() filters user_id + credits_remaining > 0
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_credits_active_lookup "
        "ON billing.user_credits (user_id, credits_remaining) "
        "WHERE credits_remaining > 0"
    )

    # History: paginated query ordered by created_at with soft-delete filter
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_operation_history_user_created "
        "ON activity.operation_history (user_id, created_at) "
        "WHERE is_deleted = false"
    )


def downgrade() -> None:
    """Remove composite indexes added in upgrade."""
    op.drop_index(
        "ix_operation_history_user_created",
        table_name="operation_history",
        schema="activity",
    )
    op.drop_index(
        "ix_user_credits_active_lookup",
        table_name="user_credits",
        schema="billing",
    )
    op.drop_index(
        "ix_user_passes_active_lookup",
        table_name="user_passes",
        schema="billing",
    )
