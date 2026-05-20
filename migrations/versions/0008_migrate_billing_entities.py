"""Create billing.subscriptions, payment_events, user_passes, user_pass_tools, user_credits.

Populates subscriptions from existing auth.users subscription_tier column.
Populates user_passes/user_pass_tools from auth.user_passes.
Populates user_credits from auth.user_credits.
Old auth tables are NOT dropped here — that happens in migration 0015.

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── billing.subscriptions ─────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tier", sa.String(20), nullable=False, server_default=sa.text("'free'")
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("razorpay_order_id", sa.String(255), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=True),
        sa.Column("amount_paid_subunits", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("region", sa.String(5), nullable=True),
        sa.Column(
            "activated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("tier IN ('free', 'pro')", name="ck_subscription_tier"),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled', 'expired', 'pending')",
            name="ck_subscription_status",
        ),
        schema="billing",
    )
    op.create_index(
        "ix_subscriptions_user_id", "subscriptions", ["user_id"], schema="billing"
    )
    # Partial unique index: one active subscription per user (enforced at DB level)
    op.execute(
        "CREATE UNIQUE INDEX uq_subscriptions_one_active_per_user "
        "ON billing.subscriptions (user_id) WHERE status = 'active'"
    )

    # ── Populate subscriptions from existing users ────────────────────────────
    # Every user gets exactly one active subscription row (tier = their current tier)
    op.execute("""
        INSERT INTO billing.subscriptions (user_id, tier, status, razorpay_payment_id)
        SELECT
            id,
            COALESCE(subscription_tier, 'free'),
            'active',
            razorpay_subscription_id
        FROM auth.users
    """)

    # ── billing.payment_events ────────────────────────────────────────────────
    op.create_table(
        "payment_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("razorpay_event_id", sa.String(255), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=True),
        sa.Column("razorpay_order_id", sa.String(255), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("item_type", sa.String(30), nullable=True),
        sa.Column("item_id", sa.String(50), nullable=True),
        sa.Column("amount_subunits", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'received'"),
        ),
        sa.Column(
            "raw_payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("processed_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'duplicate')",
            name="ck_payment_event_status",
        ),
        schema="billing",
    )
    op.create_index(
        "ix_payment_events_user_id", "payment_events", ["user_id"], schema="billing"
    )
    # Partial index for idempotency checks
    op.execute(
        "CREATE INDEX ix_payment_events_payment_id "
        "ON billing.payment_events (razorpay_payment_id) "
        "WHERE razorpay_payment_id IS NOT NULL"
    )

    # ── billing.user_passes ───────────────────────────────────────────────────
    # New home for passes; auth.user_passes stays alive until migration 0015
    op.create_table(
        "user_passes",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("pass_id", sa.String(50), nullable=False),
        sa.Column("tools_count", sa.SmallInteger(), nullable=False),
        sa.Column("uses_per_day", sa.SmallInteger(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=True),
        sa.Column(
            "purchased_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "uses_today", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("uses_reset_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pass_id"], ["billing.pass_catalog.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "source IN ('razorpay', 'earned', 'referral', 'spin', 'quest', 'welcome')",
            name="ck_pass_source",
        ),
        schema="billing",
    )
    op.create_index(
        "ix_billing_user_passes_user_id", "user_passes", ["user_id"], schema="billing"
    )
    # Partial index for active pass lookup (most frequent access-check query)
    op.execute(
        "CREATE INDEX ix_billing_user_passes_active "
        "ON billing.user_passes (user_id, expires_at) "
        "WHERE is_active = TRUE"
    )

    # ── billing.user_pass_tools ───────────────────────────────────────────────
    # Replaces tool_ids JSONB array on auth.user_passes
    op.create_table(
        "user_pass_tools",
        sa.Column("pass_instance_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(
            ["pass_instance_id"], ["billing.user_passes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("pass_instance_id", "tool_id"),
        schema="billing",
    )
    op.create_index(
        "ix_user_pass_tools_coverage",
        "user_pass_tools",
        ["pass_instance_id", "tool_id"],
        schema="billing",
    )

    # ── Migrate auth.user_passes → billing.user_passes + billing.user_pass_tools
    # uses_reset_date: cast the VARCHAR(10) date string to DATE (NULL-safe)
    op.execute(r"""
        WITH inserted AS (
            INSERT INTO billing.user_passes
                (id, user_id, pass_id, tools_count, uses_per_day, source,
                 razorpay_payment_id, purchased_at, expires_at, is_active,
                 uses_today, uses_reset_date)
            SELECT
                id,
                user_id,
                pass_id,
                tools_count,
                uses_per_day,
                source,
                razorpay_payment_id,
                purchased_at,
                expires_at,
                is_active,
                uses_today,
                CASE WHEN uses_reset_date IS NOT NULL AND uses_reset_date ~ '^\d{4}-\d{2}-\d{2}$'
                     THEN uses_reset_date::date
                     ELSE NULL END
            FROM auth.user_passes
            RETURNING id, pass_id
        )
        -- tool_ids JSONB is either ["*"] or ["tool_a","tool_b"]
        -- Insert one row per element into user_pass_tools
        INSERT INTO billing.user_pass_tools (pass_instance_id, tool_id)
        SELECT ap.id, elem
        FROM auth.user_passes ap,
             jsonb_array_elements_text(ap.tool_ids) AS elem
        WHERE EXISTS (SELECT 1 FROM inserted i WHERE i.id = ap.id)
    """)

    # ── billing.user_credits ──────────────────────────────────────────────────
    op.create_table(
        "user_credits",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("pack_id", sa.String(50), nullable=True),
        sa.Column("credits_total", sa.SmallInteger(), nullable=False),
        sa.Column("credits_remaining", sa.SmallInteger(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pack_id"], ["billing.credit_pack_catalog.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "credits_remaining >= 0 AND credits_remaining <= credits_total",
            name="ck_credits_remaining_valid",
        ),
        sa.CheckConstraint(
            "source IN ('purchase', 'streak', 'quest', 'achievement', 'referral', 'welcome', 'spin')",
            name="ck_credit_source",
        ),
        schema="billing",
    )
    op.create_index(
        "ix_billing_user_credits_user_id", "user_credits", ["user_id"], schema="billing"
    )
    # Partial index for FIFO credit drain (active credits ordered by purchase time)
    op.execute(
        "CREATE INDEX ix_billing_user_credits_active "
        "ON billing.user_credits (user_id, created_at ASC) "
        "WHERE credits_remaining > 0"
    )

    # ── Migrate auth.user_credits → billing.user_credits ─────────────────────
    op.execute("""
        INSERT INTO billing.user_credits
            (id, user_id, credits_total, credits_remaining, source, razorpay_payment_id, created_at)
        SELECT id, user_id, credits_total, credits_remaining, source, razorpay_payment_id, created_at
        FROM auth.user_credits
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_billing_user_credits_active")
    op.drop_index("ix_billing_user_credits_user_id", "user_credits", schema="billing")
    op.drop_table("user_credits", schema="billing")

    op.drop_index("ix_user_pass_tools_coverage", "user_pass_tools", schema="billing")
    op.drop_table("user_pass_tools", schema="billing")

    op.execute("DROP INDEX IF EXISTS ix_billing_user_passes_active")
    op.drop_index("ix_billing_user_passes_user_id", "user_passes", schema="billing")
    op.drop_table("user_passes", schema="billing")

    op.execute("DROP INDEX IF EXISTS ix_payment_events_payment_id")
    op.drop_index("ix_payment_events_user_id", "payment_events", schema="billing")
    op.drop_table("payment_events", schema="billing")

    op.execute("DROP INDEX IF EXISTS uq_subscriptions_one_active_per_user")
    op.drop_index("ix_subscriptions_user_id", "subscriptions", schema="billing")
    op.drop_table("subscriptions", schema="billing")
