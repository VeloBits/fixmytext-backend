"""Backfill keycloak_sub from auth.users.keycloak_id, enforce NOT NULL, add indexes.

M-1b migration: completes the work started by migration 0027 (M-1a).
Migration 0027 added nullable keycloak_sub VARCHAR(255) columns to 7 tables.
This migration populates them from the existing auth.users.keycloak_id FK,
makes them NOT NULL, and adds indexes for efficient lookup.

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-18
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (schema, table) pairs in the same order as migration 0027.
# auth.user_passes and auth.user_credits were dropped in migration 0016 and
# are excluded here; the billing schema equivalents are the live tables.
_TABLES = [
    ("activity", "user_gamification"),
    ("activity", "user_templates"),
    ("billing", "subscriptions"),
    ("billing", "payment_events"),
    ("billing", "user_passes"),
    ("billing", "user_credits"),
    ("billing", "payment_fulfillments"),
]


def upgrade() -> None:
    # Pre-check: abort if any rows have a user_id that no longer exists in
    # auth.users. The backfill silently skips such orphans, leaving keycloak_sub
    # NULL, which then causes the NOT NULL ALTER to fail with a cryptic error.
    conn = op.get_bind()
    for schema, table in _TABLES:
        result = conn.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {schema}.{table} t"
                " WHERE t.user_id IS NOT NULL"
                "   AND NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = t.user_id)"
                "   AND t.keycloak_sub IS NULL"
            )
        )
        orphan_count = result.scalar()
        if orphan_count:
            raise RuntimeError(
                f"Migration 0028 aborted: {orphan_count} orphaned row(s) in "
                f"{schema}.{table} have no matching auth.users row. "
                "Clean up or manually assign keycloak_sub before re-running."
            )

    # Step 1: Backfill keycloak_sub from auth.users.keycloak_id via user_id FK.
    # keycloak_id is a UUID column; cast to text to match VARCHAR(255).
    for schema, table in _TABLES:
        op.execute(
            sa.text(
                f"UPDATE {schema}.{table} t"
                " SET keycloak_sub = u.keycloak_id::text"
                " FROM auth.users u"
                " WHERE t.user_id = u.id"
                "   AND t.keycloak_sub IS NULL"
            )
        )

    # Step 2: Make each column NOT NULL (safe once all rows have a keycloak_sub).
    for schema, table in _TABLES:
        op.alter_column(
            table,
            "keycloak_sub",
            existing_type=sa.String(255),
            nullable=False,
            schema=schema,
        )

    # Step 3: Add indexes for efficient keycloak_sub lookups in billing queries.
    for schema, table in _TABLES:
        op.create_index(
            f"ix_{schema}_{table}_keycloak_sub",
            table,
            ["keycloak_sub"],
            schema=schema,
        )


def downgrade() -> None:
    # Reverse: drop indexes, relax NOT NULL.
    # The backfill data is left in place — it is correct and safe to keep.
    for schema, table in reversed(_TABLES):
        op.drop_index(
            f"ix_{schema}_{table}_keycloak_sub",
            table_name=table,
            schema=schema,
        )

    for schema, table in reversed(_TABLES):
        op.alter_column(
            table,
            "keycloak_sub",
            existing_type=sa.String(255),
            nullable=True,
            schema=schema,
        )
