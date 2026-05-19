"""Create billing schema with pass catalog, credit pack catalog, and regional pricing.

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Seed data from pass_catalog.py ───────────────────────────────────────────

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
    # ── Create billing schema ─────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS billing")

    # ── pass_catalog ─────────────────────────────────────────────────────────
    op.create_table(
        "pass_catalog",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("subtitle", sa.String(200), nullable=False),
        sa.Column("tools_count", sa.SmallInteger(), nullable=False),
        sa.Column("uses_per_day", sa.SmallInteger(), nullable=False),
        sa.Column("duration_days", sa.SmallInteger(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "display_order",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="billing",
    )

    # ── pass_catalog_prices ───────────────────────────────────────────────────
    op.create_table(
        "pass_catalog_prices",
        sa.Column("pass_id", sa.String(50), nullable=False),
        sa.Column("region", sa.String(5), nullable=False),
        sa.Column("amount_subunits", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.ForeignKeyConstraint(
            ["pass_id"], ["billing.pass_catalog.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("pass_id", "region"),
        sa.CheckConstraint("amount_subunits > 0", name="ck_pass_price_positive"),
        schema="billing",
    )

    # ── credit_pack_catalog ───────────────────────────────────────────────────
    op.create_table(
        "credit_pack_catalog",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("credits", sa.SmallInteger(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "display_order",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="billing",
    )

    # ── credit_pack_prices ────────────────────────────────────────────────────
    op.create_table(
        "credit_pack_prices",
        sa.Column("pack_id", sa.String(50), nullable=False),
        sa.Column("region", sa.String(5), nullable=False),
        sa.Column("amount_subunits", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.ForeignKeyConstraint(
            ["pack_id"], ["billing.credit_pack_catalog.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("pack_id", "region"),
        sa.CheckConstraint("amount_subunits > 0", name="ck_credit_price_positive"),
        schema="billing",
    )

    # ── Seed pass catalog ─────────────────────────────────────────────────────
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
    op.drop_table("credit_pack_prices", schema="billing")
    op.drop_table("credit_pack_catalog", schema="billing")
    op.drop_table("pass_catalog_prices", schema="billing")
    op.drop_table("pass_catalog", schema="billing")
    op.execute("DROP SCHEMA IF EXISTS billing CASCADE")
