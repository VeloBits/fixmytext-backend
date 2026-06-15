"""
FixMyText Account Service
=========================
Standalone FastAPI service for user account data: preferences, gamification,
templates, UI settings, favorites, tool stats, pipelines, history, and share.

Serves:
  GET/POST/PUT/DELETE /api/v1/user/*
  GET/POST/DELETE     /api/v1/history/*
  GET/POST            /api/v1/share/*

Run locally:
    uvicorn main:app --reload --port 8003
"""

import logging
from contextlib import asynccontextmanager

# Observability — must init before framework imports so SDK can patch httpx
from app.core.sentry import init_sentry
from app.core.observability_logs import init_logs_otel, shutdown_logs_otel

init_sentry()

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fixmytext_shared.middleware import (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)

from app.api.v1.router import api_router
from app.core.config import settings

# ── Logging configuration ────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

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
    pass


def _configure_logging() -> None:
    """Set up consistent logging."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    handler = logging.StreamHandler()
    if _use_json_logging:
        handler.setFormatter(
            CustomJsonFormatter("%(timestamp)s %(level)s %(name)s %(message)s")
        )
    else:
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    root.addHandler(handler)
    # Redact secrets/PII before they hit stdout, not only the OTLP handler (M-9).
    from fixmytext_shared.observability.logs import attach_log_sanitizers

    attach_log_sanitizers(handler)

    # Tame noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)

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
        uv_logger.addHandler(uv_handler)
        attach_log_sanitizers(uv_handler)  # also redact uvicorn.access query strings
        uv_logger.propagate = False


_configure_logging()

logger = logging.getLogger("fixmytext.account-svc")


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize/cleanup shared clients on startup/shutdown."""
    init_logs_otel()

    # Fail fast in prod if a security-critical setting is unset — never silently
    # run with audience/issuer verification or cookie signing disabled
    # (M-6, BE-AUTH-01, BE-AUTH-04).
    from fixmytext_shared.config.validation import assert_required_in_prod

    assert_required_in_prod(
        settings.ENVIRONMENT,
        KEYCLOAK_JWKS_URL=settings.KEYCLOAK_JWKS_URL,
        KEYCLOAK_AUDIENCE=settings.KEYCLOAK_AUDIENCE,
        KEYCLOAK_ISSUER=settings.KEYCLOAK_ISSUER,
        SESSION_COOKIE_SECRET=settings.SESSION_COOKIE_SECRET,
        # Required so the registration rate limit holds across replicas (M-4, M-8).
        REDIS_URL=settings.REDIS_URL,
    )

    from app.core.redis import close_redis, init_redis

    await init_redis()
    logger.info("account-svc ready")
    yield

    logger.info("account-svc shutting down …")
    import sentry_sdk

    sentry_sdk.flush(timeout=2.0)
    shutdown_logs_otel(timeout_millis=5000)
    await close_redis()


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="FixMyText Account Service",
    description="User account data: preferences, gamification, templates, history, share.",
    version=settings.VERSION,
    # OpenAPI docs are served only in development (BE-CFG-01).
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)

# ── Cross-cutting middleware ──────────────────────────────────────────────────
# Order matters: starlette runs middleware in REVERSE registration order.
# request → CorrelationId → SecurityHeaders → RequestLogging → app
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    SecurityHeadersMiddleware,
    is_production=settings.ENVIRONMENT == "production",
)
app.add_middleware(RequestLoggingMiddleware, logger_name="fixmytext.account-svc")

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Visitor-Id", "X-Request-ID"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


# ── Health checks ─────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
async def health_check():
    """Liveness probe used by Docker / k8s health checks."""
    return {"status": "ok", "version": settings.VERSION, "service": "account-svc"}


@app.get("/health/ready", tags=["health"])
async def readiness_check():
    """Readiness probe — verifies DB connectivity."""
    from app.db.session import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail={"status": "not ready", "error": str(exc)},
        ) from exc


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=None,
    )
