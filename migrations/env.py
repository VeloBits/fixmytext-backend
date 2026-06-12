"""Alembic environment configuration for async PostgreSQL migrations.

Model imports come from two services:
- services/payments-svc — auth + billing models (User, Subscription, passes, credits)
- services/account-svc  — activity models (preferences, gamification, history, share, etc.)

Both sys.path entries are managed carefully to avoid module-name collisions: the
account-svc import block clears and restores the `app.*` sys.modules cache so that
payments-svc remains the primary `app` namespace after both are loaded.
"""

import asyncio
import os
import re
import sys
from logging.config import fileConfig
from pathlib import Path

# ── Ensure payments-svc models are importable ────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_PAYMENTS_SVC = str(_BACKEND_ROOT / "services" / "payments-svc")
if _PAYMENTS_SVC not in sys.path:
    sys.path.insert(0, _PAYMENTS_SVC)

_SHARED_PKG = str(_BACKEND_ROOT / "shared")
if _SHARED_PKG not in sys.path:
    sys.path.insert(0, _SHARED_PKG)

# Provide a fallback DATABASE_URL so settings can be instantiated when
# alembic is invoked without a full .env (e.g. during CI offline checks).
# Development-only fallback so `alembic check` / `alembic history` work
# without a full .env present (e.g. local offline runs, pre-commit hooks).
# The real DATABASE_URL is always supplied by .env / CI secrets at runtime.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://fixmytext:fixmytext_dev@localhost:5432/fixmytext",
)

from sqlalchemy import pool  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402
from sqlalchemy.ext.asyncio import async_engine_from_config  # noqa: E402

from alembic import context  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.models import (  # noqa: E402, F401
    BillingUserCredit,
    BillingUserPass,
    CreditPackCatalog,
    CreditPackPrice,
    PassCatalog,
    PassCatalogPrice,
    PaymentEvent,
    PaymentFulfillment,
    Subscription,
    User,
    UserDailyLogin,
    UserDiscoveredTool,
    UserPassTool,
    UserSpinLog,
    UserToolUsage,
    VisitorToolUsage,
    VisitorUsage,
)
from app.db.session import Base as _payments_base  # noqa: E402

# ── Also load account-svc models (activity-schema tables not in payments-svc) ─
# We must temporarily replace `app.*` in sys.modules so account-svc's
# `from app.db.session import Base` resolves to its own declarative base
# rather than the already-cached payments-svc one.
_ACCOUNT_SVC = str(_BACKEND_ROOT / "services" / "account-svc")
_saved_app_modules: dict = {k: v for k, v in sys.modules.items() if k.startswith("app")}
for _k in list(sys.modules.keys()):
    if _k.startswith("app"):
        del sys.modules[_k]

if _ACCOUNT_SVC not in sys.path:
    sys.path.insert(0, _ACCOUNT_SVC)

from app.db.models import (  # noqa: E402, F401
    OperationHistory,
    SharedResult,
    UserFavoriteTool,
    UserGamification,
    UserPipeline,
    UserPipelineStep,
    UserPreferences,
    UserTemplate,
    UserToolStats,
    UserUiSettings,
)
from app.db.session import Base as _account_base  # noqa: E402

# Restore payments-svc as the primary `app` namespace and remove account-svc
# from sys.path to prevent future collisions.
for _k in list(sys.modules.keys()):
    if _k.startswith("app"):
        del sys.modules[_k]
sys.modules.update(_saved_app_modules)
if _ACCOUNT_SVC in sys.path:
    sys.path.remove(_ACCOUNT_SVC)

# Explicitly reference every model so static analysers (CodeQL, ruff) recognise
# these imports as intentional.  They are imported for their side-effect of
# registering each table with their service's Base.metadata.
_PAYMENTS_MODELS = [
    User,
    UserDailyLogin,
    UserSpinLog,
    UserToolUsage,
    VisitorUsage,
    VisitorToolUsage,
    UserDiscoveredTool,
    PassCatalog,
    PassCatalogPrice,
    CreditPackCatalog,
    CreditPackPrice,
    Subscription,
    PaymentEvent,
    PaymentFulfillment,
    BillingUserPass,
    UserPassTool,
    BillingUserCredit,
]
_ACCOUNT_MODELS = [
    UserPreferences,
    UserUiSettings,
    UserGamification,
    UserFavoriteTool,
    UserToolStats,
    UserTemplate,
    UserPipeline,
    UserPipelineStep,
    OperationHistory,
    SharedResult,
]

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Combine both services' metadata so autogenerate covers all tables.
target_metadata = [_payments_base.metadata, _account_base.metadata]


# ── Django-style sequential revision numbering ────────────────────────────────


def get_next_revision_number() -> str:
    """Generate Django-style sequential revision number (0001, 0002, etc.)."""
    versions_dir = Path(__file__).parent / "versions"

    if not versions_dir.exists():
        return "0001"

    existing_numbers = []
    for file in versions_dir.glob("*.py"):
        match = re.match(r"^(\d{4})_", file.name)
        if match:
            existing_numbers.append(int(match.group(1)))

    if not existing_numbers:
        return "0001"

    return f"{max(existing_numbers) + 1:04d}"


def generate_slug_from_operations(upgrade_ops) -> str:
    """Generate a descriptive slug from autogenerated migration operations."""
    if not upgrade_ops or not upgrade_ops.ops:
        return "auto"

    actions = []
    for op in upgrade_ops.ops:
        op_type = type(op).__name__

        if op_type == "CreateTableOp":
            actions.append(f"create_{op.table_name}")
        elif op_type == "DropTableOp":
            actions.append(f"drop_{op.table_name}")
        elif op_type == "AddColumnOp":
            actions.append(f"add_{op.column_name}_to_{op.table_name}")
        elif op_type == "DropColumnOp":
            actions.append(f"drop_{op.column_name}_from_{op.table_name}")
        elif op_type == "AlterColumnOp":
            actions.append(f"alter_{op.column_name}_in_{op.table_name}")
        elif op_type == "CreateIndexOp":
            actions.append(f"add_index_{op.index_name}")
        elif op_type == "DropIndexOp":
            actions.append(f"drop_index_{op.index_name}")
        elif op_type == "ModifyTableOps":
            for nested_op in op.ops:
                nested_type = type(nested_op).__name__
                if nested_type == "AddColumnOp":
                    actions.append(f"add_{nested_op.column_name}_to_{op.table_name}")
                elif nested_type == "DropColumnOp":
                    actions.append(f"drop_{nested_op.column_name}_from_{op.table_name}")
                elif nested_type == "AlterColumnOp":
                    actions.append(f"alter_{nested_op.column_name}_in_{op.table_name}")

    if not actions:
        return "auto"

    slug = "_".join(actions[:3])
    if len(actions) > 3:
        slug += "_and_more"

    slug = re.sub(r"[^a-z0-9_]", "_", slug.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:50] if len(slug) > 50 else slug


def process_revision_directives(_context, _revision, directives):
    """Replace random hash with sequential number and auto-generate slug."""
    if directives:
        for directive in directives:
            if hasattr(directive, "rev_id"):
                directive.rev_id = get_next_revision_number()

            if (
                hasattr(directive, "upgrade_ops")
                and directive.upgrade_ops
                and (not directive.message or directive.message.strip() == "")
            ):
                directive.message = generate_slug_from_operations(directive.upgrade_ops)


# ── Migration runners ─────────────────────────────────────────────────────────


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ARG001
    # Alembic's own bookkeeping table; never include in autogenerate diffs.
    if type_ == "table" and name == "alembic_version":
        return False
    # Postgres reflects unique indexes as unique constraints. We declare those
    # objects as Index(unique=True) in the models (because that's what they
    # actually are in pg_indexes — no pg_constraint row exists). Skip reflected
    # unique constraints so autogenerate doesn't ping-pong between the two forms.
    return not (type_ == "unique_constraint" and reflected)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=process_revision_directives,
        include_schemas=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        process_revision_directives=process_revision_directives,
        include_schemas=True,
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
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
