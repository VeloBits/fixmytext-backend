"""drop legacy auth.users columns (hashed_password, last_login_at)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09

Auth cut over to Keycloak-only (no local passwords, no /auth/register). Both
columns were dead: hashed_password was only ever written as NULL (JIT
provisioning) and never read; last_login_at was never read or written. Verified
zero data at risk before the drop (all rows NULL in both columns).

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "hashed_password", schema="auth")
    op.drop_column("users", "last_login_at", schema="auth")


def downgrade() -> None:
    # Re-add as nullable to match the original baseline definition.
    op.add_column(
        "users",
        sa.Column("last_login_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        schema="auth",
    )
    op.add_column(
        "users",
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        schema="auth",
    )
