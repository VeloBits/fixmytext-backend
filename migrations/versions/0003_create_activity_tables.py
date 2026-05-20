"""Create activity.user_gamification and activity.user_templates tables.

Revision ID: 0003
Create Date: 2026-03-17
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

# revision identifiers
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── activity.user_gamification ───────────────────────────────────────────
    op.create_table(
        "user_gamification",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("xp", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "streak_current", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("streak_last_date", sa.String(10), nullable=True),
        sa.Column(
            "total_ops", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_chars", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        # JSONB columns — native PostgreSQL, queryable & indexable
        sa.Column(
            "tools_used", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "discovered_tools",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "achievements",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "favorites", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "saved_pipelines",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "completed_quests",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("daily_quest_id", sa.String(50), nullable=True),
        sa.Column("daily_quest_date", sa.String(10), nullable=True),
        sa.Column(
            "daily_quest_completed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_gamification"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_user_gamification_user_id_users",
            ondelete="CASCADE",
        ),
        schema="activity",
    )

    # ── activity.user_templates ──────────────────────────────────────────────
    op.create_table(
        "user_templates",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_user_templates"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name="fk_user_templates_user_id_users",
            ondelete="CASCADE",
        ),
        schema="activity",
    )
    op.create_index(
        "ix_activity_user_templates_user_id",
        "user_templates",
        ["user_id"],
        schema="activity",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_activity_user_templates_user_id",
        table_name="user_templates",
        schema="activity",
    )
    op.drop_table("user_templates", schema="activity")
    op.drop_table("user_gamification", schema="activity")
