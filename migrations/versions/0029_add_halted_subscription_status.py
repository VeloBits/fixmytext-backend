"""Add 'halted' to billing.subscriptions status check constraint.

The subscription.halted Razorpay webhook sets status='halted' to pause
access while a payment retry is pending, but the original constraint only
allowed ('active', 'cancelled', 'expired', 'pending').  Setting an
out-of-range value raises IntegrityError → 500 → infinite Razorpay retry.

Strategy: drop-and-recreate the named check constraint to add 'halted'.
PostgreSQL does not support ALTER CHECK CONSTRAINT in-place; the drop+add
is zero-downtime for this constraint because no existing rows have
status='halted' (only status IN the old set exist), so the recreation
cannot fail.

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-19
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

try:
    from app.core.config import settings  # type: ignore[import]
except Exception:
    import os as _os

    class _FakeSettings:  # type: ignore[no-redef]
        DB_SCHEMA_BILLING: str = _os.environ.get("DB_SCHEMA_BILLING", "billing")

    settings = _FakeSettings()

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA_BILLING
TABLE = "subscriptions"
CONSTRAINT = "ck_subscription_status"


def upgrade() -> None:
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="check")
        batch_op.create_check_constraint(
            CONSTRAINT,
            sa.text(
                "status IN ('active', 'cancelled', 'expired', 'pending', 'halted')"
            ),
        )


def downgrade() -> None:
    # Remove any halted rows before reinstating the narrower constraint.
    op.execute(f"UPDATE {SCHEMA}.{TABLE} SET status='cancelled' WHERE status='halted'")
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="check")
        batch_op.create_check_constraint(
            CONSTRAINT,
            sa.text("status IN ('active', 'cancelled', 'expired', 'pending')"),
        )
