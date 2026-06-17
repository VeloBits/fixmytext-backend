"""add keycloak_id to users and make hashed_password nullable

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-19
"""

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("keycloak_id", sa.UUID(as_uuid=True), nullable=True),
        schema="auth",
    )
    op.create_unique_constraint(
        "uq_users_keycloak_id", "users", ["keycloak_id"], schema="auth"
    )
    op.create_index(
        "ix_users_keycloak_id", "users", ["keycloak_id"], unique=True, schema="auth"
    )
    op.alter_column("users", "hashed_password", nullable=True, schema="auth")


# WARNING: This downgrade will fail if any users have hashed_password=NULL (Keycloak-only accounts). Remove such rows first.
def downgrade() -> None:
    op.alter_column("users", "hashed_password", nullable=False, schema="auth")
    op.drop_index("ix_users_keycloak_id", table_name="users", schema="auth")
    op.drop_constraint("uq_users_keycloak_id", "users", schema="auth")
    op.drop_column("users", "keycloak_id", schema="auth")
