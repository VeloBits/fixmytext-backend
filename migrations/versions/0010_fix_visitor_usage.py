"""Fix visitor_usage: add visitor_tool_usage table, migrate ip_address to INET type.

Creates auth.visitor_tool_usage to replace tool_uses_today JSONB on visitor_usage.
Migrates ip_address from VARCHAR(45) to INET type.
Old columns on visitor_usage are NOT dropped here — that happens in migration 0015.

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, TIMESTAMP, UUID

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── auth.visitor_tool_usage ───────────────────────────────────────────────
    # Replaces tool_uses_today JSONB on auth.visitor_usage
    op.create_table(
        "visitor_tool_usage",
        sa.Column("visitor_id", UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["visitor_id"], ["auth.visitor_usage.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("visitor_id", "tool_id", "usage_date"),
        sa.CheckConstraint("use_count > 0", name="ck_visitor_tool_use_count_positive"),
        schema="auth",
    )
    op.create_index(
        "ix_visitor_tool_usage_visitor_date",
        "visitor_tool_usage",
        ["visitor_id", "usage_date"],
        schema="auth",
    )

    # Migrate today's usage from visitor_usage.tool_uses_today JSONB
    op.execute("""
        INSERT INTO auth.visitor_tool_usage (visitor_id, tool_id, usage_date, use_count)
        SELECT
            v.id,
            kv.key,
            CURRENT_DATE,
            LEAST(kv.value::int, 32767)
        FROM auth.visitor_usage v,
             jsonb_each_text(v.tool_uses_today) AS kv(key, value)
        WHERE v.tool_uses_today IS NOT NULL
          AND v.tool_uses_today != '{}'::jsonb
          AND v.reset_date = TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD')
          AND kv.value::int > 0
        ON CONFLICT (visitor_id, tool_id, usage_date) DO NOTHING
    """)

    # ── Migrate ip_address VARCHAR → INET ────────────────────────────────────
    # Add new INET column alongside the old VARCHAR one
    op.add_column(
        "visitor_usage",
        sa.Column("ip_address_inet", INET(), nullable=True),
        schema="auth",
    )
    # Copy valid IP addresses; skip malformed / 'unknown' values
    op.execute("""
        UPDATE auth.visitor_usage
        SET ip_address_inet = ip_address::inet
        WHERE ip_address IS NOT NULL
          AND ip_address != ''
          AND ip_address != 'unknown'
          AND ip_address ~ '^[0-9a-fA-F.:]+$'
    """)
    # Add last_seen_at column
    op.add_column(
        "visitor_usage",
        sa.Column(
            "last_seen_at",
            TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        schema="auth",
    )
    # Backfill last_seen_at from created_at
    op.execute(
        "UPDATE auth.visitor_usage SET last_seen_at = created_at WHERE last_seen_at IS NULL"
    )

    # Add GiST index on the new INET column for subnet queries
    op.execute(
        "CREATE INDEX ix_visitor_usage_ip_inet "
        "ON auth.visitor_usage USING GIST (ip_address_inet inet_ops) "
        "WHERE ip_address_inet IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_visitor_usage_ip_inet")
    op.drop_column("visitor_usage", "last_seen_at", schema="auth")
    op.drop_column("visitor_usage", "ip_address_inet", schema="auth")

    op.drop_index(
        "ix_visitor_tool_usage_visitor_date", "visitor_tool_usage", schema="auth"
    )
    op.drop_table("visitor_tool_usage", schema="auth")
