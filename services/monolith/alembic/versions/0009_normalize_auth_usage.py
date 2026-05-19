"""Normalize auth usage: user_tool_usage, user_daily_logins, user_spin_log, user_ui_settings.

Migrates today's tool usage from users.tool_uses_today JSONB.
Migrates today's login from users.daily_login_date.
Migrates last spin date from users.last_spin_date into ISO week key.
Creates empty user_ui_settings rows for all existing users.

Old columns on auth.users are NOT dropped here — that happens in migration 0015.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── auth.user_tool_usage ──────────────────────────────────────────────────
    # Replaces tool_uses_today JSONB on auth.users
    op.create_table(
        "user_tool_usage",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.Column(
            "usage_date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column(
            "use_count", sa.SmallInteger(), nullable=False, server_default=sa.text("1")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "tool_id", "usage_date"),
        sa.CheckConstraint("use_count > 0", name="ck_user_tool_use_count_positive"),
        schema="auth",
    )
    # Covering index: user_id + date → get all tool counts for a user today
    op.execute(
        "CREATE INDEX ix_user_tool_usage_user_date "
        "ON auth.user_tool_usage (user_id, usage_date) "
        "INCLUDE (tool_id, use_count)"
    )

    # Migrate today's data from users.tool_uses_today JSONB
    # Only rows where tool_uses_reset_date matches today (so counts are still valid)
    op.execute("""
        INSERT INTO auth.user_tool_usage (user_id, tool_id, usage_date, use_count)
        SELECT
            u.id,
            kv.key,
            CURRENT_DATE,
            LEAST(kv.value::int, 32767)
        FROM auth.users u,
             jsonb_each_text(u.tool_uses_today) AS kv(key, value)
        WHERE u.tool_uses_today IS NOT NULL
          AND u.tool_uses_today != '{}'::jsonb
          AND u.tool_uses_reset_date = TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
          AND kv.value::int > 0
        ON CONFLICT (user_id, tool_id, usage_date) DO NOTHING
    """)

    # ── auth.user_daily_logins ────────────────────────────────────────────────
    # Replaces daily_login_date VARCHAR(10) on auth.users
    op.create_table(
        "user_daily_logins",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "login_date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "login_date"),
        schema="auth",
    )
    op.create_index(
        "ix_user_daily_logins_user_id", "user_daily_logins", ["user_id"], schema="auth"
    )

    # Migrate today's login (only users who logged in today)
    op.execute("""
        INSERT INTO auth.user_daily_logins (user_id, login_date)
        SELECT id, CURRENT_DATE
        FROM auth.users
        WHERE daily_login_date = TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
        ON CONFLICT DO NOTHING
    """)

    # ── auth.user_spin_log ────────────────────────────────────────────────────
    # Replaces last_spin_date VARCHAR(10) on auth.users
    # Composite PK (user_id, iso_year, iso_week) enforces 1 spin per ISO week at DB level
    op.create_table(
        "user_spin_log",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("iso_year", sa.SmallInteger(), nullable=False),
        sa.Column("iso_week", sa.SmallInteger(), nullable=False),
        sa.Column("spin_date", sa.Date(), nullable=False),
        sa.Column("reward_type", sa.String(20), nullable=False),
        sa.Column("reward_ref", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "iso_year", "iso_week"),
        schema="auth",
    )
    op.create_index(
        "ix_user_spin_log_user_id", "user_spin_log", ["user_id"], schema="auth"
    )

    # Migrate last spin date (only users who spun this week, reward_type unknown — default 'credits')
    op.execute(r"""
        INSERT INTO auth.user_spin_log (user_id, iso_year, iso_week, spin_date, reward_type)
        SELECT
            id,
            EXTRACT(ISOYEAR FROM last_spin_date::date)::smallint,
            EXTRACT(WEEK    FROM last_spin_date::date)::smallint,
            last_spin_date::date,
            'credits'
        FROM auth.users
        WHERE last_spin_date IS NOT NULL
          AND last_spin_date ~ '^\d{4}-\d{2}-\d{2}$'
          AND EXTRACT(ISOYEAR FROM last_spin_date::date) = EXTRACT(ISOYEAR FROM CURRENT_DATE)
          AND EXTRACT(WEEK    FROM last_spin_date::date) = EXTRACT(WEEK    FROM CURRENT_DATE)
        ON CONFLICT DO NOTHING
    """)

    # ── auth.user_ui_settings ─────────────────────────────────────────────────
    # New table: replaces fmx_keybindings, fmx_tool_view, useResize localStorage keys
    op.create_table(
        "user_ui_settings",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tool_view", sa.String(10), nullable=False, server_default=sa.text("'grid'")
        ),
        sa.Column(
            "keybindings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "panel_sizes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema="auth",
    )

    # Create empty rows for all existing users
    op.execute("""
        INSERT INTO auth.user_ui_settings (user_id)
        SELECT id FROM auth.users
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("user_ui_settings", schema="auth")

    op.drop_index("ix_user_spin_log_user_id", "user_spin_log", schema="auth")
    op.drop_table("user_spin_log", schema="auth")

    op.drop_index("ix_user_daily_logins_user_id", "user_daily_logins", schema="auth")
    op.drop_table("user_daily_logins", schema="auth")

    op.execute("DROP INDEX IF EXISTS ix_user_tool_usage_user_date")
    op.drop_table("user_tool_usage", schema="auth")
