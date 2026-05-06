"""Create auth.password_reset_tokens table.

Stores SHA-256 hashes of password reset tokens with short-lived expiry.
Raw tokens are never persisted — only the hash — so a DB compromise cannot
be used to reset passwords.

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-20
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from alembic import op
from app.core.config import settings

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA_AUTH


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name="fk_password_reset_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_tokens_token_hash",
        table_name="password_reset_tokens",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_password_reset_tokens_user_id",
        table_name="password_reset_tokens",
        schema=SCHEMA,
    )
    op.drop_table("password_reset_tokens", schema=SCHEMA)
