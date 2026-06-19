"""Add keycloak_sub VARCHAR(255) NULL to all tables with user_id FK to auth.users.

Pre-backfill migration (M-1a). Adds nullable columns only — no data changes.
A subsequent migration (M-1b) will backfill from auth.users.keycloak_id and
then make the columns NOT NULL once all rows are populated.

Tables affected (schema.table):
  activity.user_gamification
  activity.user_templates
  billing.subscriptions
  billing.payment_events
  billing.user_passes
  billing.user_credits
  billing.payment_fulfillments

Note: auth.user_passes and auth.user_credits were dropped in migration 0016.
The billing schema equivalents (billing.user_passes, billing.user_credits) are
the live tables and are handled here.

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-17
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # activity schema
    op.add_column(
        "user_gamification",
        sa.Column("keycloak_sub", sa.String(255), nullable=True),
        schema="activity",
    )
    op.add_column(
        "user_templates",
        sa.Column("keycloak_sub", sa.String(255), nullable=True),
        schema="activity",
    )

    # billing schema
    op.add_column(
        "subscriptions",
        sa.Column("keycloak_sub", sa.String(255), nullable=True),
        schema="billing",
    )
    op.add_column(
        "payment_events",
        sa.Column("keycloak_sub", sa.String(255), nullable=True),
        schema="billing",
    )
    op.add_column(
        "user_passes",
        sa.Column("keycloak_sub", sa.String(255), nullable=True),
        schema="billing",
    )
    op.add_column(
        "user_credits",
        sa.Column("keycloak_sub", sa.String(255), nullable=True),
        schema="billing",
    )
    op.add_column(
        "payment_fulfillments",
        sa.Column("keycloak_sub", sa.String(255), nullable=True),
        schema="billing",
    )


def downgrade() -> None:
    # billing schema (reverse order)
    op.drop_column("payment_fulfillments", "keycloak_sub", schema="billing")
    op.drop_column("user_credits", "keycloak_sub", schema="billing")
    op.drop_column("user_passes", "keycloak_sub", schema="billing")
    op.drop_column("payment_events", "keycloak_sub", schema="billing")
    op.drop_column("subscriptions", "keycloak_sub", schema="billing")

    # activity schema
    op.drop_column("user_templates", "keycloak_sub", schema="activity")
    op.drop_column("user_gamification", "keycloak_sub", schema="activity")
