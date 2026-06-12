"""Add payment_fulfillments ledger for exactly-once payment fulfillment.

Creates ``billing.payment_fulfillments`` keyed by a UNIQUE ``razorpay_payment_id``
so that the synchronous client callbacks (``/passes/verify``, ``/subscription/verify``)
and the asynchronous ``payment.captured`` webhook converge on a single fulfillment
authority: the first writer inserts the ledger row and grants the entitlement; any
concurrent writer (verify-vs-webhook race) or replayed payment trips the unique
index and is short-circuited. Fixes the payment-replay (C-1) and double-grant (H-2)
revenue leaks. Mirrors the partial-unique pattern in 0020_unique_razorpay_event_id.

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-12
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op
from app.core.config import settings

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA_BILLING
AUTH = settings.DB_SCHEMA_AUTH


def upgrade() -> None:
    op.create_table(
        "payment_fulfillments",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=False),
        sa.Column("razorpay_order_id", sa.String(255), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("item_type", sa.String(30), nullable=False),
        sa.Column("item_id", sa.String(50), nullable=True),
        sa.Column("amount_subunits", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("fulfilled_via", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "result_ref",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{AUTH}.users.id"],
            name="fk_payment_fulfillments_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payment_fulfillments"),
        schema=SCHEMA,
    )
    # THE idempotency guard — exactly one fulfillment per Razorpay payment id.
    op.create_index(
        "uq_payment_fulfillments_payment_id",
        "payment_fulfillments",
        ["razorpay_payment_id"],
        unique=True,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_payment_fulfillments_user_id",
        "payment_fulfillments",
        ["user_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_fulfillments_user_id",
        table_name="payment_fulfillments",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_payment_fulfillments_payment_id",
        table_name="payment_fulfillments",
        schema=SCHEMA,
    )
    op.drop_table("payment_fulfillments", schema=SCHEMA)
