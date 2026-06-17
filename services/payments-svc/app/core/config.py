"""
Application settings for the Payments service.

Inherits cross-cutting fields (observability, Redis, CORS) from
``fixmytext_shared.config.base.BaseSharedSettings``. Payments-specific
fields live below.
"""

from fixmytext_shared.config.base import BaseSharedSettings


class Settings(BaseSharedSettings):
    # ── Service identity ──────────────────────────────────────────────────────
    OTEL_SERVICE_NAME: str = "fixmytext-payments-svc"
    VERSION: str = "0.1.0"

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"  # noqa: S104
    PORT: int = 8000
    DEBUG: bool = False

    # ── Database (same Postgres as monolith) ──────────────────────────────────
    DATABASE_URL: str
    # Right-sized for PgBouncer: 2 services * N replicas * 5+2 conns stays
    # well under Postgres max_connections (~100). Set PGBOUNCER_URL to route
    # through the pooler and use these smaller per-process pool values.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 2
    DB_POOL_RECYCLE: int = 3600
    # Optional: override DATABASE_URL with PgBouncer endpoint at runtime.
    PGBOUNCER_URL: str | None = None
    DB_SCHEMA_AUTH: str = "auth"
    DB_SCHEMA_ACTIVITY: str = "activity"
    DB_SCHEMA_BILLING: str = "billing"

    # ── Auth (JWKS from Keycloak) ─────────────────────────────────────────────
    KEYCLOAK_URL: str = ""
    KEYCLOAK_REALM: str = "fixmytext"
    KEYCLOAK_AUDIENCE: str = "fixmytext-backend"
    # Expected token issuer (Keycloak realm URL). REQUIRED in prod (startup
    # assert); empty disables issuer checks (dev only).
    KEYCLOAK_ISSUER: str = ""
    KEYCLOAK_JWKS_URL: str = ""

    # ── Razorpay ──────────────────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    FREE_USES_PER_TOOL_PER_DAY: int = 3
    DAILY_LOGIN_BONUS: int = 1
    FRONTEND_URL: str = "http://localhost:3000"
    PAYMENTS_BACKEND: str = "razorpay"

    # Anti-abuse: max referral payouts a single referrer can earn (M-10).
    REFERRAL_MAX_PER_REFERRER: int = 20


settings = Settings()
