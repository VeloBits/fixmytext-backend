"""
FixMyText FastAPI Backend
=========================
Entry point — starts the ASGI application.

Run locally:
    uvicorn main:app --reload --port 8000
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

# Observability — must init before framework imports so SDK can patch httpx/asyncpg
import sentry_sdk
from app.core.sentry import init_sentry
from app.core.observability_logs import init_logs_otel, shutdown_logs_otel

init_sentry()

import uvicorn
from alembic.config import Config as AlembicConfig
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fixmytext_shared.middleware import (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.sanitize import LogSanitizationFilter
from app.db.session import engine, get_db
from app.services.ai_service import close_groq_client, init_groq_client
from app.services.razorpay_service import init_razorpay

# ── Logging configuration ────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Try to use structured JSON logging; fall back to plain text if unavailable
_use_json_logging = False
try:
    from pythonjsonlogger.json import JsonFormatter

    class CustomJsonFormatter(JsonFormatter):
        """JSON log formatter with request context fields."""

        def add_fields(self, log_record, record, message_dict):
            super().add_fields(log_record, record, message_dict)
            log_record["timestamp"] = log_record.get("timestamp", record.created)
            log_record["level"] = record.levelname
            log_record["logger"] = record.name

    _use_json_logging = True
except ImportError:
    # python-json-logger not installed — fall back to plain text format
    pass


def _configure_logging() -> None:
    """Set up consistent logging. Called at import AND after Alembic migrations
    (which reset the root logger via fileConfig)."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove any existing handlers (e.g. from alembic fileConfig) and set ours
    root.handlers.clear()
    handler = logging.StreamHandler()
    if _use_json_logging:
        handler.setFormatter(
            CustomJsonFormatter("%(timestamp)s %(level)s %(name)s %(message)s")
        )
    else:
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    handler.addFilter(LogSanitizationFilter())
    root.addHandler(handler)

    # Tame noisy loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    # Make Uvicorn use the same format
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_handler = logging.StreamHandler()
        if _use_json_logging:
            uv_handler.setFormatter(
                CustomJsonFormatter("%(timestamp)s %(level)s %(name)s %(message)s")
            )
        else:
            uv_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
        uv_handler.addFilter(LogSanitizationFilter())
        uv_logger.addHandler(uv_handler)
        uv_logger.propagate = False


_configure_logging()

logger = logging.getLogger("fixmytext")


def _run_migrations() -> None:
    """Run Alembic migrations to head on startup."""
    alembic_cfg = AlembicConfig("alembic.ini")
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize/cleanup shared clients on startup/shutdown."""

    # ── Startup validation ───────────────────────────────────────────────
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")
    if len(settings.SECRET_KEY) < 32:
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                "SECRET_KEY must be at least 32 characters in production. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        logger.warning("SECRET_KEY is shorter than 32 characters - this is insecure")

    # Fake backends are E2E-test seams. Refuse to start in production — they
    # disable Groq and Razorpay signature/order checks and would silently
    # mint passes for free if left on.
    fake_flags = []
    if settings.AI_BACKEND.lower() == "fake":
        fake_flags.append("AI_BACKEND")
    if settings.PAYMENTS_BACKEND.lower() == "fake":
        fake_flags.append("PAYMENTS_BACKEND")
    if fake_flags:
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                f"Refusing to start: {', '.join(fake_flags)}=fake is for E2E tests only "
                "and must not be set in production."
            )
        logger.warning(
            "Fake backend(s) active: %s — E2E test mode, never deploy to prod",
            ", ".join(fake_flags),
        )

    logger.info("Running database migrations …")
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        await loop.run_in_executor(pool, _run_migrations)
    _configure_logging()  # alembic fileConfig resets root logger — reclaim it
    init_logs_otel()
    logger.info("Migrations complete")
    init_groq_client()
    logger.info("Groq client initialized")
    from app.core.redis import close_redis, init_redis

    await init_redis()
    init_razorpay()
    logger.info("Razorpay client initialized — app ready")
    yield
    logger.info("Shutting down …")
    sentry_sdk.flush(timeout=2.0)
    shutdown_logs_otel(timeout_millis=5000)
    await close_redis()
    await close_groq_client()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ── Cross-cutting middleware (lifted into fixmytext_shared.middleware) ──────
# Order matters: starlette runs middleware in REVERSE registration order, so
# the LAST add_middleware call wraps the request first. Keep this order
# stable to preserve the existing request-flow:
#   request → CorrelationId → SecurityHeaders → RequestLogging → app
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    SecurityHeadersMiddleware,
    is_production=settings.ENVIRONMENT == "production",
)
app.add_middleware(RequestLoggingMiddleware, logger_name="fixmytext")


# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Visitor-Id", "X-Request-ID"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# ── Health checks ────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
async def health_check():
    """Quick liveness probe used by Docker / k8s health checks."""
    return {"status": "ok", "version": settings.VERSION}


@app.get("/health/ready", tags=["health"])
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness check - verifies database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"status": "not ready", "database": str(e)},
        ) from e


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=None,  # use our basicConfig, not uvicorn's default
    )
