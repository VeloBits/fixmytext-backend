"""
FixMyText AI Service
====================
Standalone FastAPI service for Groq-backed AI text transformation tools.

Serves:
  POST /api/v1/ai/{tool_id}
  POST /api/v1/ai/{tool_id}/stream

Run locally:
    uvicorn main:app --reload --port 8001
"""

import logging
from contextlib import asynccontextmanager

# Observability — must init before framework imports so SDK can patch httpx
from app.core.sentry import init_sentry
from app.core.observability_logs import init_logs_otel, shutdown_logs_otel

init_sentry()

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fixmytext_shared.middleware import (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)

from app.api.v1.endpoints.ai import router as ai_router
from app.core.config import settings
from app.services.ai_service import close_groq_client, init_groq_client

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

logger = logging.getLogger("fixmytext.ai-svc")


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize/cleanup shared clients on startup/shutdown."""
    init_logs_otel()

    # Fail fast in prod if JWT audience/issuer verification would be disabled.
    from fixmytext_shared.config.validation import assert_required_in_prod

    assert_required_in_prod(
        settings.ENVIRONMENT,
        KEYCLOAK_REALM=settings.KEYCLOAK_REALM,
        KEYCLOAK_JWKS_URL=settings.KEYCLOAK_JWKS_URL,
        KEYCLOAK_AUDIENCE=settings.KEYCLOAK_AUDIENCE,
        KEYCLOAK_ISSUER=settings.KEYCLOAK_ISSUER,
        # Required so the AI rate limit holds across replicas.
        REDIS_URL=settings.REDIS_URL,
    )

    # Fake backends are E2E-test seams — refuse to start in production.
    if settings.AI_BACKEND.lower() == "fake":
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                "Refusing to start: AI_BACKEND=fake is for E2E tests only "
                "and must not be set in production."
            )
        logger.warning(
            "AI_BACKEND=fake active — E2E test mode, never deploy to prod"
        )

    init_groq_client()
    logger.info("Groq client initialized")

    from app.core.redis import close_redis, init_redis

    await init_redis()
    logger.info("ai-svc ready")
    yield

    logger.info("ai-svc shutting down …")
    import sentry_sdk

    sentry_sdk.flush(timeout=2.0)
    shutdown_logs_otel(timeout_millis=5000)
    await close_redis()
    await close_groq_client()


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="FixMyText AI Service",
    description="Groq-backed AI text transformation tools.",
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
app.add_middleware(RequestLoggingMiddleware, logger_name="fixmytext.ai-svc")

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Visitor-Id", "X-Request-ID"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ai_router, prefix="/api/v1")


# ── Health checks ─────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
async def health_check():
    """Liveness probe used by Docker / k8s health checks."""
    return {"status": "ok", "version": settings.VERSION, "service": "ai-svc"}


@app.get("/health/ready", tags=["health"])
async def readiness_check():
    """Readiness probe — verifies Groq client is initialised."""
    from app.services.ai_service import _groq_client

    groq_status = "ready" if (_groq_client is not None or not settings.GROQ_API_KEY) else "not ready"
    if groq_status == "not ready":
        raise HTTPException(
            status_code=503,
            detail={"status": "not ready", "groq": groq_status},
        )
    return {"status": "ready", "groq": groq_status}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=None,
    )
