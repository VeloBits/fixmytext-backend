"""Create PostgreSQL schemas and enable extensions.

Revision ID: 0001
Create Date: 2026-03-17
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# revision identifiers
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension (available via pgvector/pgvector Docker image)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Enable pgcrypto for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Create application schemas
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    op.execute("CREATE SCHEMA IF NOT EXISTS activity")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS activity CASCADE")
    op.execute("DROP SCHEMA IF EXISTS auth CASCADE")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS vector")
