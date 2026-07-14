"""Alembic environment for account-svc's own migration chain.

account-svc owns the identity surface (auth.users, auth.user_preferences,
auth.user_ui_settings) plus the activity-schema tables it writes. It has its OWN
migration chain and version table (public.alembic_version_account), independent of
payments-svc, but runs against the same shared Postgres.

Only ONE declarative Base is loaded here (no cross-service sys.modules swap, no
configure_mappers needed). Tables present in the metadata that this service does
NOT own — the auth.users FK target is owned here, but the read-only models
auth.user_spin_log and activity.user_discovered_tools are WRITTEN by payments-svc —
are excluded from autogenerate via include_object (see OWNED_TABLES).

Create-order note: because billing/payments tables keep cross-schema FKs to
auth.users, account-svc migrations must run BEFORE payments-svc migrations on a
fresh database.
"""

import asyncio
import os
import re
import sys
from logging.config import fileConfig
from pathlib import Path

# ── Make this service's `app` package and the shared package importable ───────
_SERVICE_ROOT = Path(__file__).resolve().parent.parent  # services/account-svc
_BACKEND_ROOT = _SERVICE_ROOT.parent.parent  # backend
for _p in (str(_SERVICE_ROOT), str(_BACKEND_ROOT / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Development-only fallback so `alembic check` / `alembic history` work without a
# full .env present (e.g. local offline runs). The real DATABASE_URL is always
# supplied by .env / CI secrets / the migrate container at runtime.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://fixmytext:fixmytext_dev@localhost:5432/fixmytext",
)

from sqlalchemy import pool  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402
from sqlalchemy.ext.asyncio import async_engine_from_config  # noqa: E402

import app.db.models  # noqa: E402, F401  (registers every model on Base.metadata)
from alembic import context  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402

# Alembic version table is service-specific so the two chains never collide on
# the shared database.
VERSION_TABLE = "alembic_version_account"

# Tables this service OWNS (creates + migrates). Everything else reachable from
# the metadata is excluded from autogenerate:
#   - read-only auth.user_spin_log / activity.user_discovered_tools (payments-svc writes them)
_AUTH = settings.DB_SCHEMA_AUTH
_ACT = settings.DB_SCHEMA_ACTIVITY
OWNED_TABLES = {
    (_AUTH, "users"),
    (_AUTH, "user_preferences"),
    (_AUTH, "user_ui_settings"),
    (_ACT, "user_templates"),
    (_ACT, "operation_history"),
    (_ACT, "shared_results"),
    (_ACT, "user_favorite_tools"),
    (_ACT, "user_pipelines"),
    (_ACT, "user_pipeline_steps"),
    (_ACT, "user_tool_stats"),
    (_ACT, "user_tool_groups"),
    (_ACT, "user_tool_group_items"),
}

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


# ── Django-style sequential revision numbering ────────────────────────────────


def get_next_revision_number() -> str:
    """Generate Django-style sequential revision number (0001, 0002, ...)."""
    versions_dir = Path(__file__).parent / "versions"
    if not versions_dir.exists():
        return "0001"
    existing = [
        int(m.group(1))
        for f in versions_dir.glob("*.py")
        if (m := re.match(r"^(\d{4})_", f.name))
    ]
    return f"{max(existing) + 1:04d}" if existing else "0001"


def process_revision_directives(_context, _revision, directives):
    """Replace the random hash with a sequential number."""
    if directives:
        for directive in directives:
            if hasattr(directive, "rev_id"):
                directive.rev_id = get_next_revision_number()


# ── Object filtering ──────────────────────────────────────────────────────────


def _owns(schema, table) -> bool:
    return (schema or "public", table) in OWNED_TABLES


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ARG001
    # Alembic's own bookkeeping tables (either chain's); never diff them.
    if type_ == "table":
        if name == "alembic_version" or name.startswith("alembic_version_"):
            return False
        return _owns(obj.schema, name)
    # Postgres reflects unique indexes as unique constraints; we declare those as
    # Index(unique=True) in models. Skip reflected unique constraints so
    # autogenerate doesn't ping-pong between the two forms.
    if type_ == "unique_constraint" and reflected:
        return False
    # Columns / indexes / FKs: include only if their parent table is owned.
    parent = getattr(obj, "table", None)
    if parent is not None:
        return _owns(parent.schema, parent.name)
    return True


# ── Migration runners ─────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=process_revision_directives,
        include_schemas=True,
        include_object=include_object,
        version_table=VERSION_TABLE,
        version_table_schema="public",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        process_revision_directives=process_revision_directives,
        include_schemas=True,
        version_table=VERSION_TABLE,
        version_table_schema="public",
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
