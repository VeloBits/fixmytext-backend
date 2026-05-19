"""create passes, credits, visitor_usage tables and update users

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-17 10:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
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
    # ── user_passes ──────────────────────────────────────────────────────────
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
        sa.Column(
            "tool_ids", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("tools_count", sa.Integer(), nullable=False),
        sa.Column("uses_per_day", sa.Integer(), nullable=False),
        sa.Column(
            "uses_today", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("uses_reset_date", sa.String(10), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column(
            "purchased_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="auth",
    )
    op.create_index("ix_user_passes_user_id", "user_passes", ["user_id"], schema="auth")
    op.create_index(
        "ix_user_passes_active_lookup",
        "user_passes",
        ["user_id", "is_active", "expires_at"],
        schema="auth",
    )

    # ── user_credits ─────────────────────────────────────────────────────────
    op.create_table(
        "user_credits",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("credits_total", sa.Integer(), nullable=False),
        sa.Column("credits_remaining", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("razorpay_payment_id", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="auth",
    )
    op.create_index(
        "ix_user_credits_user_id", "user_credits", ["user_id"], schema="auth"
    )
    op.create_index(
        "ix_user_credits_active_lookup",
        "user_credits",
        ["user_id", "credits_remaining"],
        schema="auth",
    )
    op.create_check_constraint(
        "ck_credits_remaining_valid",
        "user_credits",
        "credits_remaining >= 0 AND credits_remaining <= credits_total",
        schema="auth",
    )

    # ── visitor_usage ────────────────────────────────────────────────────────
    op.create_table(
        "visitor_usage",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column(
            "tool_uses_today",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("reset_date", sa.String(10), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="auth",
    )
    op.create_index(
        "ix_visitor_usage_fingerprint", "visitor_usage", ["fingerprint"], schema="auth"
    )
    op.create_index(
        "ix_visitor_usage_ip_address", "visitor_usage", ["ip_address"], schema="auth"
    )

    # ── Update users table ───────────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "tool_uses_today",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
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
    op.add_column(
        "users", sa.Column("referral_code", sa.String(20), nullable=True), schema="auth"
    )
    op.add_column(
        "users",
        sa.Column("referred_by", UUID(as_uuid=True), nullable=True),
        schema="auth",
    )
    op.add_column(
        "users", sa.Column("region", sa.String(5), nullable=True), schema="auth"
    )
    op.create_unique_constraint(
        "uq_users_referral_code", "users", ["referral_code"], schema="auth"
    )
    op.create_foreign_key(
        "fk_users_referred_by",
        "users",
        "users",
        ["referred_by"],
        ["id"],
        source_schema="auth",
        referent_schema="auth",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_users_referred_by", "users", schema="auth", type_="foreignkey"
    )
    op.drop_constraint("uq_users_referral_code", "users", schema="auth", type_="unique")
    op.drop_column("users", "region", schema="auth")
    op.drop_column("users", "referred_by", schema="auth")
    op.drop_column("users", "referral_code", schema="auth")
    op.drop_column("users", "last_spin_date", schema="auth")
    op.drop_column("users", "daily_login_date", schema="auth")
    op.drop_column("users", "tool_uses_reset_date", schema="auth")
    op.drop_column("users", "tool_uses_today", schema="auth")

    op.drop_index("ix_visitor_usage_ip_address", "visitor_usage", schema="auth")
    op.drop_index("ix_visitor_usage_fingerprint", "visitor_usage", schema="auth")
    op.drop_table("visitor_usage", schema="auth")

    op.drop_constraint(
        "ck_credits_remaining_valid", "user_credits", schema="auth", type_="check"
    )
    op.drop_index("ix_user_credits_active_lookup", "user_credits", schema="auth")
    op.drop_index("ix_user_credits_user_id", "user_credits", schema="auth")
    op.drop_table("user_credits", schema="auth")

    op.drop_index("ix_user_passes_active_lookup", "user_passes", schema="auth")
    op.drop_index("ix_user_passes_user_id", "user_passes", schema="auth")
    op.drop_table("user_passes", schema="auth")
