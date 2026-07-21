"""Backfill subscriptions.expires_at for the Pro 30-day expiry model.

Pro used to be granted forever: fulfillment never wrote expires_at and no
query filtered on it, so one payment meant lifetime access. Access is now
gated on ``status IN ('active','cancelled') AND expires_at > now()``, so
every legacy pro row needs a concrete expiry — 30 days from activation,
matching what those customers actually paid for.

Revision ID: 0003
Revises: 0002

"""

from typing import Union
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE billing.subscriptions
        SET expires_at = activated_at + interval '30 days'
        WHERE tier = 'pro'
          AND status IN ('active', 'cancelled')
          AND expires_at IS NULL
        """
    )


def downgrade() -> None:
    # Intentionally a no-op: backfilled values are indistinguishable from
    # expiries written by the application after this migration, so reverting
    # them would corrupt legitimate data.
    pass
