"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-06-24 15:02:28.131273

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Billing catalog seed data (carried verbatim from the old migration 0007) ──
# Reference data the app reads; not model-derivable, so seeded here by hand.

_PASSES = [
    # Micro Passes
    {
        "id": "quick_fix",
        "name": "Quick Fix",
        "subtitle": "3 extra uses · 1 tool · today",
        "tools_count": 1,
        "uses_per_day": 3,
        "duration_days": 1,
        "display_order": 1,
        "prices": {
            "IN": (200, "inr"),
            "US": (50, "usd"),
            "GB": (40, "gbp"),
            "EU": (50, "eur"),
        },
    },
    {
        "id": "tinkerer",
        "name": "Tinkerer",
        "subtitle": "10 uses · 1 tool · today",
        "tools_count": 1,
        "uses_per_day": 10,
        "duration_days": 1,
        "display_order": 2,
        "prices": {
            "IN": (500, "inr"),
            "US": (75, "usd"),
            "GB": (60, "gbp"),
            "EU": (75, "eur"),
        },
    },
    {
        "id": "double_dip",
        "name": "Double Dip",
        "subtitle": "10 uses · 2 tools · today",
        "tools_count": 2,
        "uses_per_day": 10,
        "duration_days": 1,
        "display_order": 3,
        "prices": {
            "IN": (800, "inr"),
            "US": (99, "usd"),
            "GB": (80, "gbp"),
            "EU": (99, "eur"),
        },
    },
    # Day Passes
    {
        "id": "day_single",
        "name": "Day Single",
        "subtitle": "20 uses · 1 tool · 1 day",
        "tools_count": 1,
        "uses_per_day": 20,
        "duration_days": 1,
        "display_order": 4,
        "prices": {
            "IN": (1000, "inr"),
            "US": (149, "usd"),
            "GB": (120, "gbp"),
            "EU": (149, "eur"),
        },
    },
    {
        "id": "day_triple",
        "name": "Day Triple",
        "subtitle": "20 uses · 3 tools · 1 day",
        "tools_count": 3,
        "uses_per_day": 20,
        "duration_days": 1,
        "display_order": 5,
        "prices": {
            "IN": (2500, "inr"),
            "US": (249, "usd"),
            "GB": (200, "gbp"),
            "EU": (249, "eur"),
        },
    },
    {
        "id": "day_five",
        "name": "Day Five",
        "subtitle": "30 uses · 5 tools · 1 day",
        "tools_count": 5,
        "uses_per_day": 30,
        "duration_days": 1,
        "display_order": 6,
        "prices": {
            "IN": (3500, "inr"),
            "US": (300, "usd"),
            "GB": (250, "gbp"),
            "EU": (300, "eur"),
        },
    },
    {
        "id": "day_ten",
        "name": "Day Ten",
        "subtitle": "40 uses · 10 tools · 1 day",
        "tools_count": 10,
        "uses_per_day": 40,
        "duration_days": 1,
        "display_order": 7,
        "prices": {
            "IN": (5900, "inr"),
            "US": (500, "usd"),
            "GB": (400, "gbp"),
            "EU": (500, "eur"),
        },
    },
    {
        "id": "day_fifteen",
        "name": "Day Fifteen",
        "subtitle": "50 uses · 15 tools · 1 day",
        "tools_count": 15,
        "uses_per_day": 50,
        "duration_days": 1,
        "display_order": 8,
        "prices": {
            "IN": (7900, "inr"),
            "US": (700, "usd"),
            "GB": (560, "gbp"),
            "EU": (700, "eur"),
        },
    },
    {
        "id": "day_all",
        "name": "Day All",
        "subtitle": "50 uses · all tools · 1 day",
        "tools_count": -1,
        "uses_per_day": 50,
        "duration_days": 1,
        "display_order": 9,
        "prices": {
            "IN": (9900, "inr"),
            "US": (800, "usd"),
            "GB": (640, "gbp"),
            "EU": (800, "eur"),
        },
    },
    # Multi-Day Passes
    {
        "id": "sprint_single",
        "name": "Sprint Single",
        "subtitle": "20 uses/day · 1 tool · 5 days",
        "tools_count": 1,
        "uses_per_day": 20,
        "duration_days": 5,
        "display_order": 10,
        "prices": {
            "IN": (3900, "inr"),
            "US": (300, "usd"),
            "GB": (250, "gbp"),
            "EU": (300, "eur"),
        },
    },
    {
        "id": "sprint_triple",
        "name": "Sprint Triple",
        "subtitle": "25 uses/day · 3 tools · 5 days",
        "tools_count": 3,
        "uses_per_day": 25,
        "duration_days": 5,
        "display_order": 11,
        "prices": {
            "IN": (8900, "inr"),
            "US": (700, "usd"),
            "GB": (560, "gbp"),
            "EU": (700, "eur"),
        },
    },
    {
        "id": "sprint_five",
        "name": "Sprint Five",
        "subtitle": "30 uses/day · 5 tools · 5 days",
        "tools_count": 5,
        "uses_per_day": 30,
        "duration_days": 5,
        "display_order": 12,
        "prices": {
            "IN": (12900, "inr"),
            "US": (1000, "usd"),
            "GB": (800, "gbp"),
            "EU": (1000, "eur"),
        },
    },
    {
        "id": "sprint_all",
        "name": "Sprint All",
        "subtitle": "50 uses/day · all tools · 5 days",
        "tools_count": -1,
        "uses_per_day": 50,
        "duration_days": 5,
        "display_order": 13,
        "prices": {
            "IN": (19900, "inr"),
            "US": (1500, "usd"),
            "GB": (1200, "gbp"),
            "EU": (1500, "eur"),
        },
    },
    {
        "id": "marathon_five",
        "name": "Marathon Five",
        "subtitle": "40 uses/day · 5 tools · 10 days",
        "tools_count": 5,
        "uses_per_day": 40,
        "duration_days": 10,
        "display_order": 14,
        "prices": {
            "IN": (19900, "inr"),
            "US": (1500, "usd"),
            "GB": (1200, "gbp"),
            "EU": (1500, "eur"),
        },
    },
    {
        "id": "marathon_all",
        "name": "Marathon All",
        "subtitle": "60 uses/day · all tools · 10 days",
        "tools_count": -1,
        "uses_per_day": 60,
        "duration_days": 10,
        "display_order": 15,
        "prices": {
            "IN": (34900, "inr"),
            "US": (2500, "usd"),
            "GB": (2000, "gbp"),
            "EU": (2500, "eur"),
        },
    },
    {
        "id": "stretch_all",
        "name": "Stretch All",
        "subtitle": "80 uses/day · all tools · 20 days",
        "tools_count": -1,
        "uses_per_day": 80,
        "duration_days": 20,
        "display_order": 16,
        "prices": {
            "IN": (54900, "inr"),
            "US": (4000, "usd"),
            "GB": (3200, "gbp"),
            "EU": (4000, "eur"),
        },
    },
    # Monthly Passes
    {
        "id": "monthly_five",
        "name": "Monthly Five",
        "subtitle": "50 uses/day · 5 tools · 30 days",
        "tools_count": 5,
        "uses_per_day": 50,
        "duration_days": 30,
        "display_order": 17,
        "prices": {
            "IN": (29900, "inr"),
            "US": (2000, "usd"),
            "GB": (1600, "gbp"),
            "EU": (2000, "eur"),
        },
    },
    {
        "id": "monthly_ten",
        "name": "Monthly Ten",
        "subtitle": "75 uses/day · 10 tools · 30 days",
        "tools_count": 10,
        "uses_per_day": 75,
        "duration_days": 30,
        "display_order": 18,
        "prices": {
            "IN": (49900, "inr"),
            "US": (3500, "usd"),
            "GB": (2800, "gbp"),
            "EU": (3500, "eur"),
        },
    },
    {
        "id": "monthly_all",
        "name": "Monthly All",
        "subtitle": "100 uses/day · all tools · 30 days",
        "tools_count": -1,
        "uses_per_day": 100,
        "duration_days": 30,
        "display_order": 19,
        "prices": {
            "IN": (79900, "inr"),
            "US": (5500, "usd"),
            "GB": (4400, "gbp"),
            "EU": (5500, "eur"),
        },
    },
    # Long-Term Passes
    {
        "id": "season_all",
        "name": "Season Pass",
        "subtitle": "150 uses/day · all tools · 90 days",
        "tools_count": -1,
        "uses_per_day": 150,
        "duration_days": 90,
        "display_order": 20,
        "prices": {
            "IN": (149900, "inr"),
            "US": (9900, "usd"),
            "GB": (7900, "gbp"),
            "EU": (9900, "eur"),
        },
    },
    {
        "id": "half_year",
        "name": "Half Year",
        "subtitle": "200 uses/day · all tools · 180 days",
        "tools_count": -1,
        "uses_per_day": 200,
        "duration_days": 180,
        "display_order": 21,
        "prices": {
            "IN": (249900, "inr"),
            "US": (15000, "usd"),
            "GB": (12000, "gbp"),
            "EU": (15000, "eur"),
        },
    },
    {
        "id": "annual",
        "name": "Annual",
        "subtitle": "200 uses/day · all tools · 365 days",
        "tools_count": -1,
        "uses_per_day": 200,
        "duration_days": 365,
        "display_order": 22,
        "prices": {
            "IN": (399900, "inr"),
            "US": (20000, "usd"),
            "GB": (16000, "gbp"),
            "EU": (20000, "eur"),
        },
    },
]

_CREDIT_PACKS = [
    {
        "id": "credits_5",
        "name": "Ink Drop",
        "credits": 5,
        "display_order": 1,
        "prices": {
            "IN": (500, "inr"),
            "US": (99, "usd"),
            "GB": (80, "gbp"),
            "EU": (99, "eur"),
        },
    },
    {
        "id": "credits_15",
        "name": "Ink Pot",
        "credits": 15,
        "display_order": 2,
        "prices": {
            "IN": (1200, "inr"),
            "US": (249, "usd"),
            "GB": (200, "gbp"),
            "EU": (249, "eur"),
        },
    },
    {
        "id": "credits_50",
        "name": "Ink Well",
        "credits": 50,
        "display_order": 3,
        "prices": {
            "IN": (3500, "inr"),
            "US": (499, "usd"),
            "GB": (400, "gbp"),
            "EU": (499, "eur"),
        },
    },
    {
        "id": "credits_150",
        "name": "Ink Barrel",
        "credits": 150,
        "display_order": 4,
        "prices": {
            "IN": (8900, "inr"),
            "US": (799, "usd"),
            "GB": (640, "gbp"),
            "EU": (799, "eur"),
        },
    },
]


def upgrade() -> None:
    # Schemas + extension are not model-derivable; created here by hand. Idempotent
    # (IF NOT EXISTS) so order vs. the account-svc chain on the shared DB is safe.
    # payments-svc is the create-order-second chain: account-svc creates auth.users
    # first, which the billing/usage tables below FK into.
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    op.execute("CREATE SCHEMA IF NOT EXISTS activity")
    op.execute("CREATE SCHEMA IF NOT EXISTS billing")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "visitor_usage",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visitor_usage")),
        schema="auth",
    )
    op.create_index(
        "ix_visitor_usage_fingerprint",
        "visitor_usage",
        ["fingerprint"],
        unique=False,
        schema="auth",
    )
    op.create_index(
        "ix_visitor_usage_ip_inet",
        "visitor_usage",
        ["ip_address"],
        unique=False,
        schema="auth",
        postgresql_using="gist",
        postgresql_ops={"ip_address": "inet_ops"},
        postgresql_where=sa.text("ip_address IS NOT NULL"),
    )
    op.create_table(
        "credit_pack_catalog",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("credits", sa.SmallInteger(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "display_order",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_pack_catalog")),
        schema="billing",
    )
    op.create_table(
        "pass_catalog",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("subtitle", sa.String(length=200), nullable=False),
        sa.Column("tools_count", sa.SmallInteger(), nullable=False),
        sa.Column("uses_per_day", sa.SmallInteger(), nullable=False),
        sa.Column("duration_days", sa.SmallInteger(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "display_order",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pass_catalog")),
        schema="billing",
    )
    op.create_table(
        "user_discovered_tools",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tool_id", sa.String(length=100), nullable=False),
        sa.Column(
            "discovered_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_discovered_tools_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "tool_id", name=op.f("pk_user_discovered_tools")
        ),
        schema="activity",
    )
    op.create_index(
        "ix_user_discovered_tools_user_id",
        "user_discovered_tools",
        ["user_id"],
        unique=False,
        schema="activity",
    )
    op.create_table(
        "user_daily_logins",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "login_date",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_daily_logins_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "login_date", name=op.f("pk_user_daily_logins")
        ),
        schema="auth",
    )
    op.create_index(
        "ix_user_daily_logins_user_id",
        "user_daily_logins",
        ["user_id"],
        unique=False,
        schema="auth",
    )
    op.create_table(
        "user_spin_log",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("iso_year", sa.SmallInteger(), nullable=False),
        sa.Column("iso_week", sa.SmallInteger(), nullable=False),
        sa.Column("spin_date", sa.Date(), nullable=False),
        sa.Column("reward_type", sa.String(length=20), nullable=False),
        sa.Column("reward_ref", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_spin_log_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "iso_year", "iso_week", name=op.f("pk_user_spin_log")
        ),
        schema="auth",
    )
    op.create_index(
        "ix_user_spin_log_user_id",
        "user_spin_log",
        ["user_id"],
        unique=False,
        schema="auth",
    )
    op.create_table(
        "user_tool_usage",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tool_id", sa.String(length=100), nullable=False),
        sa.Column(
            "usage_date",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column(
            "use_count", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.CheckConstraint(
            "use_count > 0",
            name=op.f("ck_user_tool_usage_ck_user_tool_use_count_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_tool_usage_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "tool_id", "usage_date", name=op.f("pk_user_tool_usage")
        ),
        schema="auth",
    )
    op.create_index(
        "ix_user_tool_usage_user_date",
        "user_tool_usage",
        ["user_id", "usage_date"],
        unique=False,
        schema="auth",
        postgresql_include=["tool_id", "use_count"],
    )
    op.create_table(
        "visitor_tool_usage",
        sa.Column("visitor_id", sa.UUID(), nullable=False),
        sa.Column("tool_id", sa.String(length=100), nullable=False),
        sa.Column(
            "usage_date",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column(
            "use_count", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["visitor_id"],
            ["auth.visitor_usage.id"],
            name=op.f("fk_visitor_tool_usage_visitor_id_visitor_usage"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "visitor_id", "tool_id", "usage_date", name=op.f("pk_visitor_tool_usage")
        ),
        schema="auth",
    )
    op.create_index(
        "ix_visitor_tool_usage_visitor_date",
        "visitor_tool_usage",
        ["visitor_id", "usage_date"],
        unique=False,
        schema="auth",
    )
    op.create_table(
        "credit_pack_prices",
        sa.Column("pack_id", sa.String(length=50), nullable=False),
        sa.Column("region", sa.String(length=5), nullable=False),
        sa.Column("amount_subunits", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "amount_subunits > 0",
            name=op.f("ck_credit_pack_prices_ck_credit_price_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["pack_id"],
            ["billing.credit_pack_catalog.id"],
            name=op.f("fk_credit_pack_prices_pack_id_credit_pack_catalog"),
        ),
        sa.PrimaryKeyConstraint(
            "pack_id", "region", name=op.f("pk_credit_pack_prices")
        ),
        schema="billing",
    )
    op.create_table(
        "pass_catalog_prices",
        sa.Column("pass_id", sa.String(length=50), nullable=False),
        sa.Column("region", sa.String(length=5), nullable=False),
        sa.Column("amount_subunits", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "amount_subunits > 0",
            name=op.f("ck_pass_catalog_prices_ck_pass_price_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["pass_id"],
            ["billing.pass_catalog.id"],
            name=op.f("fk_pass_catalog_prices_pass_id_pass_catalog"),
        ),
        sa.PrimaryKeyConstraint(
            "pass_id", "region", name=op.f("pk_pass_catalog_prices")
        ),
        schema="billing",
    )
    op.create_table(
        "payment_events",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("razorpay_event_id", sa.String(length=255), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=True),
        sa.Column("razorpay_order_id", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("keycloak_sub", sa.String(length=255), nullable=False),
        sa.Column("item_type", sa.String(length=30), nullable=True),
        sa.Column("item_id", sa.String(length=50), nullable=True),
        sa.Column("amount_subunits", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'received'"),
            nullable=False,
        ),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("processed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'duplicate')",
            name=op.f("ck_payment_events_ck_payment_event_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_payment_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
        schema="billing",
    )
    op.create_index(
        "ix_billing_payment_events_keycloak_sub",
        "payment_events",
        ["keycloak_sub"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        "ix_payment_events_payment_id",
        "payment_events",
        ["razorpay_payment_id"],
        unique=False,
        schema="billing",
        postgresql_where=sa.text("razorpay_payment_id IS NOT NULL"),
    )
    op.create_index(
        "ix_payment_events_razorpay_event_id",
        "payment_events",
        ["razorpay_event_id"],
        unique=True,
        schema="billing",
        postgresql_where=sa.text("razorpay_event_id IS NOT NULL"),
    )
    op.create_index(
        "ix_payment_events_user_id",
        "payment_events",
        ["user_id"],
        unique=False,
        schema="billing",
    )
    op.create_table(
        "payment_fulfillments",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=False),
        sa.Column("razorpay_order_id", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("keycloak_sub", sa.String(length=255), nullable=False),
        sa.Column("item_type", sa.String(length=30), nullable=False),
        sa.Column("item_id", sa.String(length=50), nullable=True),
        sa.Column("amount_subunits", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("fulfilled_via", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "result_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_payment_fulfillments_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_fulfillments")),
        schema="billing",
    )
    op.create_index(
        "ix_billing_payment_fulfillments_keycloak_sub",
        "payment_fulfillments",
        ["keycloak_sub"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        "ix_payment_fulfillments_user_id",
        "payment_fulfillments",
        ["user_id"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        "uq_payment_fulfillments_payment_id",
        "payment_fulfillments",
        ["razorpay_payment_id"],
        unique=True,
        schema="billing",
    )
    op.create_table(
        "subscriptions",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("keycloak_sub", sa.String(length=255), nullable=False),
        sa.Column(
            "tier",
            sa.String(length=20),
            server_default=sa.text("'free'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("razorpay_order_id", sa.String(length=255), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=True),
        sa.Column("amount_paid_subunits", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("region", sa.String(length=5), nullable=True),
        sa.Column(
            "activated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled', 'expired', 'pending', 'halted')",
            name=op.f("ck_subscriptions_ck_subscription_status"),
        ),
        sa.CheckConstraint(
            "tier IN ('free', 'pro')",
            name=op.f("ck_subscriptions_ck_subscription_tier"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        schema="billing",
    )
    op.create_index(
        "ix_billing_subscriptions_keycloak_sub",
        "subscriptions",
        ["keycloak_sub"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        "ix_subscriptions_user_id",
        "subscriptions",
        ["user_id"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        "uq_subscriptions_one_active_per_user",
        "subscriptions",
        ["user_id"],
        unique=True,
        schema="billing",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "user_credits",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("keycloak_sub", sa.String(length=255), nullable=False),
        sa.Column("pack_id", sa.String(length=50), nullable=True),
        sa.Column("credits_total", sa.SmallInteger(), nullable=False),
        sa.Column("credits_remaining", sa.SmallInteger(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('purchase', 'streak', 'quest', 'achievement', 'referral', 'welcome', 'spin')",
            name=op.f("ck_user_credits_ck_credit_source"),
        ),
        sa.CheckConstraint(
            "credits_remaining >= 0 AND credits_remaining <= credits_total",
            name=op.f("ck_user_credits_ck_credits_remaining_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["pack_id"],
            ["billing.credit_pack_catalog.id"],
            name=op.f("fk_user_credits_pack_id_credit_pack_catalog"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_credits_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_credits")),
        schema="billing",
    )
    op.create_index(
        "ix_billing_user_credits_active",
        "user_credits",
        ["user_id", "created_at"],
        unique=False,
        schema="billing",
        postgresql_where=sa.text("credits_remaining > 0"),
    )
    op.create_index(
        "ix_billing_user_credits_keycloak_sub",
        "user_credits",
        ["keycloak_sub"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        op.f("ix_billing_user_credits_user_id"),
        "user_credits",
        ["user_id"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        "ix_user_credits_active_lookup",
        "user_credits",
        ["user_id", "credits_remaining"],
        unique=False,
        schema="billing",
        postgresql_where=sa.text("credits_remaining > 0"),
    )
    op.create_table(
        "user_passes",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("keycloak_sub", sa.String(length=255), nullable=False),
        sa.Column("pass_id", sa.String(length=50), nullable=False),
        sa.Column("tools_count", sa.SmallInteger(), nullable=False),
        sa.Column("uses_per_day", sa.SmallInteger(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=True),
        sa.Column(
            "purchased_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "uses_today", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("uses_reset_date", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "source IN ('razorpay', 'earned', 'referral', 'spin', 'quest', 'welcome')",
            name=op.f("ck_user_passes_ck_pass_source"),
        ),
        sa.ForeignKeyConstraint(
            ["pass_id"],
            ["billing.pass_catalog.id"],
            name=op.f("fk_user_passes_pass_id_pass_catalog"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_passes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_passes")),
        schema="billing",
    )
    op.create_index(
        "ix_billing_user_passes_keycloak_sub",
        "user_passes",
        ["keycloak_sub"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        "ix_billing_user_passes_user_id",
        "user_passes",
        ["user_id"],
        unique=False,
        schema="billing",
    )
    op.create_index(
        "ix_user_passes_active_lookup",
        "user_passes",
        ["user_id", "expires_at"],
        unique=False,
        schema="billing",
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_table(
        "user_pass_tools",
        sa.Column("pass_instance_id", sa.UUID(), nullable=False),
        sa.Column("tool_id", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["pass_instance_id"],
            ["billing.user_passes.id"],
            name=op.f("fk_user_pass_tools_pass_instance_id_user_passes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "pass_instance_id", "tool_id", name=op.f("pk_user_pass_tools")
        ),
        schema="billing",
    )
    op.create_index(
        "ix_user_pass_tools_coverage",
        "user_pass_tools",
        ["pass_instance_id", "tool_id"],
        unique=False,
        schema="billing",
    )
    # ### end Alembic commands ###

    # ── Seed the billing catalog (carried verbatim from old migration 0007) ──────
    conn = op.get_bind()
    for p in _PASSES:
        conn.execute(
            sa.text(
                "INSERT INTO billing.pass_catalog (id, name, subtitle, tools_count, uses_per_day, duration_days, display_order) "
                "VALUES (:id, :name, :subtitle, :tools_count, :uses_per_day, :duration_days, :display_order)"
            ),
            {
                "id": p["id"],
                "name": p["name"],
                "subtitle": p["subtitle"],
                "tools_count": p["tools_count"],
                "uses_per_day": p["uses_per_day"],
                "duration_days": p["duration_days"],
                "display_order": p["display_order"],
            },
        )
        for region, (amount, currency) in p["prices"].items():
            conn.execute(
                sa.text(
                    "INSERT INTO billing.pass_catalog_prices (pass_id, region, amount_subunits, currency) "
                    "VALUES (:pass_id, :region, :amount_subunits, :currency)"
                ),
                {
                    "pass_id": p["id"],
                    "region": region,
                    "amount_subunits": amount,
                    "currency": currency,
                },
            )

    for c in _CREDIT_PACKS:
        conn.execute(
            sa.text(
                "INSERT INTO billing.credit_pack_catalog (id, name, credits, display_order) "
                "VALUES (:id, :name, :credits, :display_order)"
            ),
            {
                "id": c["id"],
                "name": c["name"],
                "credits": c["credits"],
                "display_order": c["display_order"],
            },
        )
        for region, (amount, currency) in c["prices"].items():
            conn.execute(
                sa.text(
                    "INSERT INTO billing.credit_pack_prices (pack_id, region, amount_subunits, currency) "
                    "VALUES (:pack_id, :region, :amount_subunits, :currency)"
                ),
                {
                    "pack_id": c["id"],
                    "region": region,
                    "amount_subunits": amount,
                    "currency": currency,
                },
            )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        "ix_user_pass_tools_coverage", table_name="user_pass_tools", schema="billing"
    )
    op.drop_table("user_pass_tools", schema="billing")
    op.drop_index(
        "ix_user_passes_active_lookup",
        table_name="user_passes",
        schema="billing",
        postgresql_where=sa.text("is_active = true"),
    )
    op.drop_index(
        "ix_billing_user_passes_user_id", table_name="user_passes", schema="billing"
    )
    op.drop_index(
        "ix_billing_user_passes_keycloak_sub",
        table_name="user_passes",
        schema="billing",
    )
    op.drop_table("user_passes", schema="billing")
    op.drop_index(
        "ix_user_credits_active_lookup",
        table_name="user_credits",
        schema="billing",
        postgresql_where=sa.text("credits_remaining > 0"),
    )
    op.drop_index(
        op.f("ix_billing_user_credits_user_id"),
        table_name="user_credits",
        schema="billing",
    )
    op.drop_index(
        "ix_billing_user_credits_keycloak_sub",
        table_name="user_credits",
        schema="billing",
    )
    op.drop_index(
        "ix_billing_user_credits_active",
        table_name="user_credits",
        schema="billing",
        postgresql_where=sa.text("credits_remaining > 0"),
    )
    op.drop_table("user_credits", schema="billing")
    op.drop_index(
        "uq_subscriptions_one_active_per_user",
        table_name="subscriptions",
        schema="billing",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index(
        "ix_subscriptions_user_id", table_name="subscriptions", schema="billing"
    )
    op.drop_index(
        "ix_billing_subscriptions_keycloak_sub",
        table_name="subscriptions",
        schema="billing",
    )
    op.drop_table("subscriptions", schema="billing")
    op.drop_index(
        "uq_payment_fulfillments_payment_id",
        table_name="payment_fulfillments",
        schema="billing",
    )
    op.drop_index(
        "ix_payment_fulfillments_user_id",
        table_name="payment_fulfillments",
        schema="billing",
    )
    op.drop_index(
        "ix_billing_payment_fulfillments_keycloak_sub",
        table_name="payment_fulfillments",
        schema="billing",
    )
    op.drop_table("payment_fulfillments", schema="billing")
    op.drop_index(
        "ix_payment_events_user_id", table_name="payment_events", schema="billing"
    )
    op.drop_index(
        "ix_payment_events_razorpay_event_id",
        table_name="payment_events",
        schema="billing",
        postgresql_where=sa.text("razorpay_event_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_payment_events_payment_id",
        table_name="payment_events",
        schema="billing",
        postgresql_where=sa.text("razorpay_payment_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_billing_payment_events_keycloak_sub",
        table_name="payment_events",
        schema="billing",
    )
    op.drop_table("payment_events", schema="billing")
    op.drop_table("pass_catalog_prices", schema="billing")
    op.drop_table("credit_pack_prices", schema="billing")
    op.drop_index(
        "ix_visitor_tool_usage_visitor_date",
        table_name="visitor_tool_usage",
        schema="auth",
    )
    op.drop_table("visitor_tool_usage", schema="auth")
    op.drop_index(
        "ix_user_tool_usage_user_date",
        table_name="user_tool_usage",
        schema="auth",
        postgresql_include=["tool_id", "use_count"],
    )
    op.drop_table("user_tool_usage", schema="auth")
    op.drop_index("ix_user_spin_log_user_id", table_name="user_spin_log", schema="auth")
    op.drop_table("user_spin_log", schema="auth")
    op.drop_index(
        "ix_user_daily_logins_user_id", table_name="user_daily_logins", schema="auth"
    )
    op.drop_table("user_daily_logins", schema="auth")
    op.drop_index(
        "ix_user_discovered_tools_user_id",
        table_name="user_discovered_tools",
        schema="activity",
    )
    op.drop_table("user_discovered_tools", schema="activity")
    op.drop_table("pass_catalog", schema="billing")
    op.drop_table("credit_pack_catalog", schema="billing")
    op.drop_index(
        "ix_visitor_usage_ip_inet",
        table_name="visitor_usage",
        schema="auth",
        postgresql_using="gist",
        postgresql_ops={"ip_address": "inet_ops"},
        postgresql_where=sa.text("ip_address IS NOT NULL"),
    )
    op.drop_index(
        "ix_visitor_usage_fingerprint", table_name="visitor_usage", schema="auth"
    )
    op.drop_table("visitor_usage", schema="auth")
    # ### end Alembic commands ###
