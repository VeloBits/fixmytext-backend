"""
Declarative base, async engine, and session factory for PostgreSQL.

Configures connection pooling via settings (pool_size, max_overflow,
pool_recycle) to control resource usage and connection lifetime.

payments-svc connects to the SAME Postgres as the monolith and uses the
same schemas (auth, billing, activity). It does NOT run Alembic migrations
— those stay in the monolith.
"""

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Naming convention for constraints — keeps generated names consistent
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Route through PgBouncer when PGBOUNCER_URL is configured, falling back to
# the direct DATABASE_URL. This allows zero-code-change switching between
# pooled and direct connections via environment variable.
engine_url = settings.PGBOUNCER_URL or settings.DATABASE_URL

engine = create_async_engine(
    engine_url,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
