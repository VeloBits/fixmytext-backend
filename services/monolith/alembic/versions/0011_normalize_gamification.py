"""Normalize gamification: user_tool_stats, user_discovered_tools, user_favorite_tools,
user_pipelines, user_pipeline_steps. Fix string date columns to DATE. Upgrade total_chars to BIGINT.

Old JSONB columns on activity.user_gamification are NOT dropped here — that happens in migration 0015.

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── activity.user_tool_stats ──────────────────────────────────────────────
    # Replaces tools_used JSONB dict on user_gamification
    op.create_table(
        "user_tool_stats",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.Column(
            "total_uses", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "last_used_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "tool_id"),
        sa.CheckConstraint("total_uses > 0", name="ck_user_tool_stats_uses_positive"),
        schema="activity",
    )
    # Index for "top tools per user" query (DESC requires raw DDL)
    op.execute(
        "CREATE INDEX ix_user_tool_stats_user_uses "
        "ON activity.user_tool_stats (user_id, total_uses DESC)"
    )

    # Migrate tools_used JSONB dict {tool_id: count} → rows
    op.execute("""
        INSERT INTO activity.user_tool_stats (user_id, tool_id, total_uses)
        SELECT
            g.user_id,
            kv.key,
            GREATEST(kv.value::int, 1)
        FROM activity.user_gamification g,
             jsonb_each_text(g.tools_used) AS kv(key, value)
        WHERE g.tools_used IS NOT NULL
          AND g.tools_used != '{}'::jsonb
          AND kv.value::int > 0
        ON CONFLICT (user_id, tool_id) DO UPDATE SET total_uses = EXCLUDED.total_uses
    """)

    # ── activity.user_discovered_tools ────────────────────────────────────────
    # Replaces discovered_tools JSONB array on user_gamification
    op.create_table(
        "user_discovered_tools",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.Column(
            "discovered_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "tool_id"),
        schema="activity",
    )
    op.create_index(
        "ix_user_discovered_tools_user_id",
        "user_discovered_tools",
        ["user_id"],
        schema="activity",
    )

    # Migrate discovered_tools JSONB array → rows
    # discovered_at defaults to now() since historical timestamps are not available
    op.execute("""
        INSERT INTO activity.user_discovered_tools (user_id, tool_id)
        SELECT g.user_id, elem
        FROM activity.user_gamification g,
             jsonb_array_elements_text(g.discovered_tools) AS elem
        WHERE g.discovered_tools IS NOT NULL
          AND jsonb_array_length(g.discovered_tools) > 0
        ON CONFLICT DO NOTHING
    """)

    # ── activity.user_favorite_tools ──────────────────────────────────────────
    # Replaces favorites JSONB array on user_gamification
    op.create_table(
        "user_favorite_tools",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.Column(
            "sort_order", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "tool_id"),
        schema="activity",
    )
    op.create_index(
        "ix_user_favorite_tools_user_id",
        "user_favorite_tools",
        ["user_id"],
        schema="activity",
    )

    # Migrate favorites JSONB array → rows (preserve array order as sort_order)
    op.execute("""
        INSERT INTO activity.user_favorite_tools (user_id, tool_id, sort_order)
        SELECT g.user_id, elem.value, elem.ordinality - 1
        FROM activity.user_gamification g,
             jsonb_array_elements_text(g.favorites) WITH ORDINALITY AS elem(value, ordinality)
        WHERE g.favorites IS NOT NULL
          AND jsonb_array_length(g.favorites) > 0
        ON CONFLICT DO NOTHING
    """)

    # ── activity.user_pipelines ───────────────────────────────────────────────
    # Replaces saved_pipelines JSONB array on user_gamification
    op.create_table(
        "user_pipelines",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="activity",
    )
    op.execute(
        "CREATE INDEX ix_user_pipelines_user_active "
        "ON activity.user_pipelines (user_id) WHERE is_active = TRUE"
    )

    # ── activity.user_pipeline_steps ─────────────────────────────────────────
    op.create_table(
        "user_pipeline_steps",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("pipeline_id", UUID(as_uuid=True), nullable=False),
        sa.Column("step_order", sa.SmallInteger(), nullable=False),
        sa.Column("tool_id", sa.String(100), nullable=False),
        sa.Column("tool_label", sa.String(200), nullable=False),
        sa.Column("config", JSONB, nullable=True),
        sa.ForeignKeyConstraint(
            ["pipeline_id"], ["activity.user_pipelines.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pipeline_id", "step_order", name="uq_pipeline_step_order"),
        schema="activity",
    )
    op.create_index(
        "ix_user_pipeline_steps_pipeline",
        "user_pipeline_steps",
        ["pipeline_id", "step_order"],
        schema="activity",
    )

    # Migrate saved_pipelines JSONB
    # Each element in the array is expected to be: {name, steps: [{tool_id, tool_label, config?}]}
    # We migrate as best-effort; malformed entries are skipped.
    op.execute("""
        WITH pipeline_rows AS (
            SELECT
                g.user_id,
                gen_random_uuid() AS pipeline_id,
                COALESCE(pipeline_elem->>'name', 'Pipeline ' || (ordinality::text)) AS pipeline_name,
                pipeline_elem->'steps' AS steps_json,
                ordinality
            FROM activity.user_gamification g,
                 jsonb_array_elements(g.saved_pipelines) WITH ORDINALITY AS t(pipeline_elem, ordinality)
            WHERE g.saved_pipelines IS NOT NULL
              AND jsonb_array_length(g.saved_pipelines) > 0
              AND jsonb_typeof(pipeline_elem) = 'object'
        ),
        inserted_pipelines AS (
            INSERT INTO activity.user_pipelines (id, user_id, name)
            SELECT pipeline_id, user_id, pipeline_name
            FROM pipeline_rows
            RETURNING id, user_id
        )
        INSERT INTO activity.user_pipeline_steps (pipeline_id, step_order, tool_id, tool_label, config)
        SELECT
            pr.pipeline_id,
            (step_elem.ordinality - 1)::smallint,
            COALESCE(step_elem.step->>'tool_id', step_elem.step->>'id', 'unknown'),
            COALESCE(step_elem.step->>'tool_label', step_elem.step->>'label', 'Tool'),
            CASE
                WHEN step_elem.step - 'tool_id' - 'id' - 'tool_label' - 'label' != '{}'::jsonb
                THEN step_elem.step - 'tool_id' - 'id' - 'tool_label' - 'label'
                ELSE NULL
            END
        FROM pipeline_rows pr,
             jsonb_array_elements(pr.steps_json) WITH ORDINALITY AS step_elem(step, ordinality)
        WHERE jsonb_typeof(pr.steps_json) = 'array'
          AND jsonb_array_length(pr.steps_json) > 0
    """)

    # ── Fix streak_last_date: VARCHAR(10) → add DATE column ──────────────────
    op.add_column(
        "user_gamification",
        sa.Column("streak_last_date_new", sa.Date(), nullable=True),
        schema="activity",
    )
    op.execute(r"""
        UPDATE activity.user_gamification
        SET streak_last_date_new = streak_last_date::date
        WHERE streak_last_date IS NOT NULL
          AND streak_last_date ~ '^\d{4}-\d{2}-\d{2}$'
    """)

    # ── Fix daily_quest_date: VARCHAR(10) → add DATE column ──────────────────
    op.add_column(
        "user_gamification",
        sa.Column("daily_quest_date_new", sa.Date(), nullable=True),
        schema="activity",
    )
    op.execute(r"""
        UPDATE activity.user_gamification
        SET daily_quest_date_new = daily_quest_date::date
        WHERE daily_quest_date IS NOT NULL
          AND daily_quest_date ~ '^\d{4}-\d{2}-\d{2}$'
    """)

    # ── Upgrade total_chars: INTEGER → BIGINT ─────────────────────────────────
    op.alter_column(
        "user_gamification",
        "total_chars",
        type_=sa.BigInteger(),
        schema="activity",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # ── GIN indexes for kept JSONB (achievements, completed_quests) ───────────
    op.execute(
        "CREATE INDEX ix_gamification_achievements_gin "
        "ON activity.user_gamification USING GIN (achievements)"
    )
    op.execute(
        "CREATE INDEX ix_gamification_completed_quests_gin "
        "ON activity.user_gamification USING GIN (completed_quests)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_gamification_completed_quests_gin")
    op.execute("DROP INDEX IF EXISTS ix_gamification_achievements_gin")

    op.alter_column(
        "user_gamification",
        "total_chars",
        type_=sa.Integer(),
        schema="activity",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )

    op.drop_column("user_gamification", "daily_quest_date_new", schema="activity")
    op.drop_column("user_gamification", "streak_last_date_new", schema="activity")

    op.drop_index(
        "ix_user_pipeline_steps_pipeline", "user_pipeline_steps", schema="activity"
    )
    op.drop_table("user_pipeline_steps", schema="activity")

    op.execute("DROP INDEX IF EXISTS ix_user_pipelines_user_active")
    op.drop_table("user_pipelines", schema="activity")

    op.drop_index(
        "ix_user_favorite_tools_user_id", "user_favorite_tools", schema="activity"
    )
    op.drop_table("user_favorite_tools", schema="activity")

    op.drop_index(
        "ix_user_discovered_tools_user_id", "user_discovered_tools", schema="activity"
    )
    op.drop_table("user_discovered_tools", schema="activity")

    op.execute("DROP INDEX IF EXISTS activity.ix_user_tool_stats_user_uses")
    op.drop_table("user_tool_stats", schema="activity")
