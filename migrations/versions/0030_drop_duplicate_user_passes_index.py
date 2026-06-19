"""Drop duplicate ix_billing_user_passes_active index.

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-19

ix_billing_user_passes_active (migration 0008) and ix_user_passes_active_lookup
(migration 0019) are identical partial indexes on (user_id, expires_at) WHERE
is_active = true.  Keeping both wastes write amplification on every pass INSERT,
UPDATE, and DELETE.  ix_user_passes_active_lookup is the canonical name; the
older ix_billing_user_passes_active is removed.

No data is affected.  The index can be recreated by the downgrade path.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

SCHEMA = "billing"
INDEX = "ix_billing_user_passes_active"
TABLE = "user_passes"


def upgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.{INDEX}")


def downgrade() -> None:
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX} "
        f"ON {SCHEMA}.{TABLE} (user_id, expires_at) "
        f"WHERE is_active = true"
    )
