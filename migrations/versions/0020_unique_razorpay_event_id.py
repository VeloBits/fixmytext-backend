"""Add unique index on payment_events.razorpay_event_id.

Ensures webhook idempotency at the database level — duplicate Razorpay
events are rejected even if the application-level check has a race window.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-14
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# ``settings`` is only used for schema name constants.  Import it from the
# environment when available; fall back to a lightweight stub so this migration
# can be introspected (``alembic history``, ``alembic check``) without a
# running payments-svc import chain.
try:
    from app.core.config import settings  # type: ignore[import]
except Exception:
    import os as _os

    class _FakeSettings:  # type: ignore[no-redef]
        DATABASE_URL: str = _os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://fixmytext:fixmytext_dev@localhost:5432/fixmytext",
        )
        DB_SCHEMA_BILLING: str = _os.environ.get("DB_SCHEMA_BILLING", "billing")
        DB_SCHEMA_AUTH: str = _os.environ.get("DB_SCHEMA_AUTH", "auth")

    settings = _FakeSettings()

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA_BILLING


def upgrade() -> None:
    op.create_index(
        "ix_payment_events_razorpay_event_id",
        "payment_events",
        ["razorpay_event_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where="razorpay_event_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_events_razorpay_event_id",
        table_name="payment_events",
        schema=SCHEMA,
    )
