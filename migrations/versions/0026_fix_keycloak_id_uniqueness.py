"""Drop redundant named UNIQUE constraint on auth.users.keycloak_id.

Migration 0024 created three overlapping uniqueness enforcements on keycloak_id:
  1. ORM column-level unique=True  -> unnamed unique index (removed in ORM models)
  2. op.create_unique_constraint("uq_users_keycloak_id") -> named UNIQUE constraint
  3. op.create_index("ix_users_keycloak_id", unique=True) -> named unique index (kept)

This migration drops the redundant named constraint (#2), leaving only the named
unique index ix_users_keycloak_id as the single uniqueness enforcer.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-17
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_users_keycloak_id", "users", schema="auth", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_users_keycloak_id", "users", ["keycloak_id"], schema="auth"
    )
