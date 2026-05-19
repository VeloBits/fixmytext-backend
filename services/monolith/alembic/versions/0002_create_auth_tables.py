"""Create auth.users and auth.user_preferences tables.

Revision ID: 0002
Create Date: 2026-03-17
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from alembic import op

# revision identifiers
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── auth.users ───────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Subscription fields
        sa.Column(
            "subscription_tier",
            sa.String(20),
            server_default=sa.text("'free'"),
            nullable=False,
        ),
        sa.Column("razorpay_subscription_id", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        schema="auth",
    )
    op.create_index("ix_auth_users_email", "users", ["email"], schema="auth")

    # ── auth.user_preferences ────────────────────────────────────────────────
    op.create_table(
        "user_preferences",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "theme", sa.String(10), server_default=sa.text("'dark'"), nullable=False
        ),
        sa.Column("persona", sa.String(50), nullable=True),
        sa.Column("theme_skin", sa.String(50), nullable=True),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_preferences"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_user_preferences_user_id_users",
            ondelete="CASCADE",
        ),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_table("user_preferences", schema="auth")
    op.drop_index("ix_auth_users_email", table_name="users", schema="auth")
    op.drop_table("users", schema="auth")
