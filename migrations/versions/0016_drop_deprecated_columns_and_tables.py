"""drop deprecated columns and legacy tables

Revision ID: 0016
Revises: 0015
Create Date: 2026-03-30 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
__all__ = [
    "revision",
    "down_revision",
    "branch_labels",
    "depends_on",
    "upgrade",
    "downgrade",
]


def upgrade() -> None:
    # ── 1. Drop deprecated columns from auth.users ───────────────────────────
    op.drop_column("users", "subscription_tier", schema="auth")
    op.drop_column("users", "razorpay_subscription_id", schema="auth")
    op.drop_column("users", "tool_uses_today", schema="auth")
    op.drop_column("users", "tool_uses_reset_date", schema="auth")
    op.drop_column("users", "daily_login_date", schema="auth")
    op.drop_column("users", "last_spin_date", schema="auth")

    # ── 2. Drop deprecated columns from activity.user_gamification ────────────
    op.drop_column("user_gamification", "tools_used", schema="activity")
    op.drop_column("user_gamification", "discovered_tools", schema="activity")
    op.drop_column("user_gamification", "favorites", schema="activity")
    op.drop_column("user_gamification", "saved_pipelines", schema="activity")
    op.drop_column("user_gamification", "streak_last_date", schema="activity")
    op.drop_column("user_gamification", "daily_quest_date", schema="activity")

    # ── 3. Rename _new columns to final names in activity.user_gamification ───
    op.alter_column(
        "user_gamification",
        "streak_last_date_new",
        new_column_name="streak_last_date",
        schema="activity",
    )
    op.alter_column(
        "user_gamification",
        "daily_quest_date_new",
        new_column_name="daily_quest_date",
        schema="activity",
    )

    # ── 4. Drop deprecated columns from auth.visitor_usage ────────────────────
    op.drop_column("visitor_usage", "ip_address", schema="auth")
    op.drop_column("visitor_usage", "tool_uses_today", schema="auth")
    op.drop_column("visitor_usage", "reset_date", schema="auth")
    op.drop_column("visitor_usage", "last_seen_at", schema="auth")

    # ── 5. Rename ip_address_inet to ip_address in auth.visitor_usage ─────────
    op.alter_column(
        "visitor_usage", "ip_address_inet", new_column_name="ip_address", schema="auth"
    )

    # ── 6. Drop legacy tables ─────────────────────────────────────────────────
    op.drop_table("user_passes", schema="auth")
    op.drop_table("user_credits", schema="auth")


def downgrade() -> None:
    # ── 6. Recreate legacy tables ─────────────────────────────────────────────
    op.create_table(
        "user_passes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pass_id", sa.String(50), nullable=False),
        sa.Column(
            "tool_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        sa.Column("tools_count", sa.Integer(), nullable=False),
        sa.Column("uses_per_day", sa.Integer(), nullable=False),
        sa.Column(
            "uses_today", sa.Integer(), server_default=sa.text("0"), nullable=True
        ),
        sa.Column("uses_reset_date", sa.String(10), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column(
            "purchased_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=True
        ),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        schema="auth",
    )
    op.create_index(
        "ix_auth_user_passes_user_id", "user_passes", ["user_id"], schema="auth"
    )

    op.create_table(
        "user_credits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credits_total", sa.Integer(), nullable=False),
        sa.Column("credits_remaining", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        schema="auth",
    )
    op.create_index(
        "ix_auth_user_credits_user_id", "user_credits", ["user_id"], schema="auth"
    )

    # ── 5. Rename ip_address back to ip_address_inet ──────────────────────────
    op.alter_column(
        "visitor_usage", "ip_address", new_column_name="ip_address_inet", schema="auth"
    )

    # ── 4. Re-add deprecated columns to auth.visitor_usage ────────────────────
    op.add_column(
        "visitor_usage",
        sa.Column(
            "ip_address",
            sa.String(45),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        schema="auth",
    )
    op.create_index(
        "ix_auth_visitor_usage_ip_address",
        "visitor_usage",
        ["ip_address"],
        schema="auth",
    )
    op.add_column(
        "visitor_usage",
        sa.Column(
            "tool_uses_today",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        schema="auth",
    )
    op.add_column(
        "visitor_usage",
        sa.Column("reset_date", sa.String(10), nullable=True),
        schema="auth",
    )
    op.add_column(
        "visitor_usage",
        sa.Column(
            "last_seen_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        schema="auth",
    )

    # ── 3. Rename columns back to _new suffixed names ─────────────────────────
    op.alter_column(
        "user_gamification",
        "streak_last_date",
        new_column_name="streak_last_date_new",
        schema="activity",
    )
    op.alter_column(
        "user_gamification",
        "daily_quest_date",
        new_column_name="daily_quest_date_new",
        schema="activity",
    )

    # ── 2. Re-add deprecated columns to activity.user_gamification ────────────
    op.add_column(
        "user_gamification",
        sa.Column(
            "tools_used",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        schema="activity",
    )
    op.add_column(
        "user_gamification",
        sa.Column(
            "discovered_tools",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        schema="activity",
    )
    op.add_column(
        "user_gamification",
        sa.Column(
            "favorites",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        schema="activity",
    )
    op.add_column(
        "user_gamification",
        sa.Column(
            "saved_pipelines",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        schema="activity",
    )
    op.add_column(
        "user_gamification",
        sa.Column("streak_last_date", sa.String(10), nullable=True),
        schema="activity",
    )
    op.add_column(
        "user_gamification",
        sa.Column("daily_quest_date", sa.String(10), nullable=True),
        schema="activity",
    )

    # ── 1. Re-add deprecated columns to auth.users ────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "subscription_tier",
            sa.String(20),
            server_default=sa.text("'free'"),
            nullable=True,
        ),
        schema="auth",
    )
    op.add_column(
        "users",
        sa.Column("razorpay_subscription_id", sa.String(255), nullable=True),
        schema="auth",
    )
    op.add_column(
        "users",
        sa.Column(
            "tool_uses_today",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        schema="auth",
    )
    op.add_column(
        "users",
        sa.Column("tool_uses_reset_date", sa.String(10), nullable=True),
        schema="auth",
    )
    op.add_column(
        "users",
        sa.Column("daily_login_date", sa.String(10), nullable=True),
        schema="auth",
    )
    op.add_column(
        "users",
        sa.Column("last_spin_date", sa.String(10), nullable=True),
        schema="auth",
    )
