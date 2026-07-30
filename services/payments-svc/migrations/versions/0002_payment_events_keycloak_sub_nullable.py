"""payment_events.keycloak_sub nullable

Webhook events can reference an unknown user or none at all (user_id is
already nullable with ON DELETE SET NULL), so the denormalized Keycloak
subject cannot be required on this table. The four entitlement tables
(payment_fulfillments, user_passes, user_credits, subscriptions) keep it
NOT NULL - those rows always belong to a resolved user.

Revision ID: 0002
Revises: 0001

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "payment_events",
        "keycloak_sub",
        existing_type=sa.String(length=255),
        nullable=True,
        schema="billing",
    )


def downgrade() -> None:
    op.alter_column(
        "payment_events",
        "keycloak_sub",
        existing_type=sa.String(length=255),
        nullable=False,
        schema="billing",
    )
