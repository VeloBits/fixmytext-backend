"""Add unique index on payment_events.razorpay_event_id.

Ensures webhook idempotency at the database level — duplicate Razorpay
events are rejected even if the application-level check has a race window.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-14
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
from app.core.config import settings

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA_BILLING


def upgrade() -> None:
    op.create_index(
        "ix_payment_events_razorpay_event_id",
        "payment_events",
        ["razorpay_event_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where="razorpay_event_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_events_razorpay_event_id",
        table_name="payment_events",
        schema=SCHEMA,
    )
