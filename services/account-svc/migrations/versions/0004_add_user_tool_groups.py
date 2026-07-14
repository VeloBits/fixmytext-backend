"""add user tool groups; onboarding_seen; seed starter groups from personas

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-14

Personas were replaced by user-created custom tool groups on 2026-07-14. This
migration:

1. Creates activity.user_tool_groups + activity.user_tool_group_items (named,
   ordered per-user groups of tool ids).
2. Adds auth.user_ui_settings.onboarding_seen and backfills it to true for
   every user with a non-null persona — they already answered the (old)
   onboarding picker and must not be re-prompted by the new starter-kit modal.
3. Seeds one starter group per user from their persona, snapshotting the
   persona → suggested-tools mapping that lived in the frontend registry
   (tools-registry PERSONAS, now STARTER_KITS — names must stay in sync).
   'explorer' deliberately seeds nothing (it never had suggested tools).

auth.user_preferences.persona is intentionally NOT dropped here — stale
deployed bundles still read it. Drop it in a later migration once none do.

downgrade() removes the tables and the column: seeded AND user-created groups
are lost (structure-only restore, same policy as 0003).

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Snapshot of the frontend persona → starter-kit mapping at removal time.
# Group names must match STARTER_KITS in frontend/packages/tools-registry.
_STARTER_KITS = {
    "writer": (
        "Writing essentials",
        ["fix_grammar", "paraphrase", "change_tone", "proofread"],
    ),
    "student": ("Study essentials", ["summarize", "eli5", "translate"]),
    "developer": (
        "Developer toolkit",
        ["json_fmt", "regex_test", "base64_enc", "jwt_decode"],
    ),
    "social": (
        "Social media kit",
        ["hashtags", "seo_titles", "tweet_shorten", "meta_desc"],
    ),
}


def upgrade() -> None:
    op.create_table(
        "user_tool_groups",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "sort_order", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth.users.id"],
            name=op.f("fk_user_tool_groups_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_tool_groups")),
        sa.UniqueConstraint("user_id", "name", name="uq_user_tool_groups_user_name"),
        schema="activity",
    )
    op.create_index(
        "ix_user_tool_groups_user_id",
        "user_tool_groups",
        ["user_id"],
        unique=False,
        schema="activity",
    )

    op.create_table(
        "user_tool_group_items",
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("tool_id", sa.String(length=100), nullable=False),
        sa.Column(
            "sort_order", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["activity.user_tool_groups.id"],
            name=op.f("fk_user_tool_group_items_group_id_user_tool_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "group_id", "tool_id", name=op.f("pk_user_tool_group_items")
        ),
        schema="activity",
    )
    op.create_index(
        "ix_user_tool_group_items_group_id",
        "user_tool_group_items",
        ["group_id"],
        unique=False,
        schema="activity",
    )

    op.add_column(
        "user_ui_settings",
        sa.Column(
            "onboarding_seen",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema="auth",
    )

    # Anyone with a persona (including 'explorer' = dismissed) already answered
    # the old onboarding picker; never re-prompt them.
    op.execute(
        """
        INSERT INTO auth.user_ui_settings (user_id, onboarding_seen)
        SELECT user_id, true FROM auth.user_preferences WHERE persona IS NOT NULL
        ON CONFLICT (user_id) DO UPDATE SET onboarding_seen = true
        """
    )

    # Seed one editable starter group per persona user so the "For You" section
    # they had yesterday is a custom group today.
    for persona, (group_name, tool_ids) in _STARTER_KITS.items():
        op.execute(
            f"""
            INSERT INTO activity.user_tool_groups (user_id, name, sort_order)
            SELECT user_id, '{group_name}', 0
            FROM auth.user_preferences WHERE persona = '{persona}'
            """
        )
        values = ", ".join(
            f"('{tool_id}', {order})" for order, tool_id in enumerate(tool_ids)
        )
        op.execute(
            f"""
            INSERT INTO activity.user_tool_group_items (group_id, tool_id, sort_order)
            SELECT g.id, t.tool_id, t.ord
            FROM activity.user_tool_groups g
            JOIN auth.user_preferences p
              ON p.user_id = g.user_id AND p.persona = '{persona}'
            CROSS JOIN (VALUES {values}) AS t(tool_id, ord)
            WHERE g.name = '{group_name}'
            """
        )


def downgrade() -> None:
    op.drop_column("user_ui_settings", "onboarding_seen", schema="auth")
    op.drop_index(
        "ix_user_tool_group_items_group_id",
        table_name="user_tool_group_items",
        schema="activity",
    )
    op.drop_table("user_tool_group_items", schema="activity")
    op.drop_index(
        "ix_user_tool_groups_user_id",
        table_name="user_tool_groups",
        schema="activity",
    )
    op.drop_table("user_tool_groups", schema="activity")
