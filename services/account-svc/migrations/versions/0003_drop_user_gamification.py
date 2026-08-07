"""drop activity.user_gamification (gamification feature removed)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-13

The gamification feature (XP, streaks, achievements, daily quests) was removed
on 2026-07-13. The frontend soft-delete is already deployed, and the two
/user/gamification endpoints are now DB-free no-op stubs kept only as a shield
for stale cached SPA bundles. The reward economy (spin wheel, daily-login
bonus) is NOT affected - its tables are owned elsewhere and untouched.

Data loss is deliberate: downgrade() recreates the table and its three indexes
with the exact structure from 0001_baseline, but the dropped rows are NOT
restorable.

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_gamification_achievements_gin",
        table_name="user_gamification",
        schema="activity",
        postgresql_using="gin",
    )
    op.drop_index(
        "ix_gamification_completed_quests_gin",
        table_name="user_gamification",
        schema="activity",
        postgresql_using="gin",
    )
    op.drop_index(
        "ix_activity_user_gamification_keycloak_sub",
        table_name="user_gamification",
        schema="activity",
    )
    op.drop_table("user_gamification", schema="activity")


def downgrade() -> None:
    # Structure-only restore (mirrors 0001_baseline); data is not recoverable.
    op.create_table(
        "user_gamification",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("keycloak_sub", sa.String(length=255), nullable=False),
        sa.Column("xp", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "streak_current", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("streak_last_date", sa.Date(), nullable=True),
        sa.Column("daily_quest_date", sa.Date(), nullable=True),
        sa.Column(
            "total_ops", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_chars", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "achievements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "completed_quests",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("daily_quest_id", sa.String(length=50), nullable=True),
        sa.Column(
            "daily_quest_completed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_gamification_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_gamification")),
        schema="activity",
    )
    op.create_index(
        "ix_activity_user_gamification_keycloak_sub",
        "user_gamification",
        ["keycloak_sub"],
        unique=False,
        schema="activity",
    )
    op.create_index(
        "ix_gamification_achievements_gin",
        "user_gamification",
        ["achievements"],
        unique=False,
        schema="activity",
        postgresql_using="gin",
    )
    op.create_index(
        "ix_gamification_completed_quests_gin",
        "user_gamification",
        ["completed_quests"],
        unique=False,
        schema="activity",
        postgresql_using="gin",
    )
