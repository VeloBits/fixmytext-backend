"""
Application settings loaded from environment variables via pydantic-settings.

Create a '.env' file in /backend (copy from '.env.example') to override defaults.

Inherits cross-cutting fields (observability, Redis, CORS, rate limits) from
``fixmytext_shared.config.base.BaseSharedSettings``. Monolith-specific fields
(SECRET_KEY, GROQ, RAZORPAY, EMAIL, DB, JWT, Keycloak) live below.
"""

from fixmytext_shared.config.base import BaseSharedSettings


class Settings(BaseSharedSettings):
    # ── Project metadata ──────────────────────────────────────────────────────
    PROJECT_NAME: str = "FixMyText API"
    PROJECT_DESCRIPTION: str = (
        "RESTful backend for the FixMyText text-manipulation application."
    )
    VERSION: str = "0.1.0"

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"  # noqa: S104
    PORT: int = 8000
    DEBUG: bool = False

    # ── API ───────────────────────────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"

    # ── AI / Groq ─────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    AI_BACKEND: str = "auto"
    PAYMENTS_BACKEND: str = "razorpay"

    # ── Rate limiting (monolith-specific extras; shared base has the cross-cutting two) ──
    AUTH_RATE_LIMIT_MAX: int = 50
    VISITOR_RATE_LIMIT_MAX: int = 25

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # JWT algorithm — RS256 for Keycloak-issued tokens verified via JWKS.
    JWT_ALGORITHM: str = "RS256"

    # ── Keycloak (dormant; activated when the auth cutover lands) ────────────
    KEYCLOAK_URL: str = ""
    KEYCLOAK_REALM: str = ""
    KEYCLOAK_AUDIENCE: str = ""
    KEYCLOAK_JWKS_URL: str = ""
    KEYCLOAK_ADMIN: str = "admin"

    # ── Auth / Cookies ───────────────────────────────────────────────────────
    COOKIE_SECURE: bool = True
    COOKIE_NAME: str = "refresh_token"
    COOKIE_PATH: str = "/api/v1/auth"

    # ── Razorpay ───────────────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    FREE_USES_PER_TOOL_PER_DAY: int = 3
    DAILY_LOGIN_BONUS: int = 1
    FRONTEND_URL: str = "http://localhost:3000"

    # ── Share ─────────────────────────────────────────────────────────────────
    SHARE_EXPIRE_DAYS: int = 30
    MAX_SHARE_TEXT_LENGTH: int = 50_000

    # ── History ───────────────────────────────────────────────────────────────
    HISTORY_PREVIEW_MAX_LENGTH: int = 500

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600

    # ── PostgreSQL schemas ───────────────────────────────────────────────────
    DB_SCHEMA_AUTH: str = "auth"
    DB_SCHEMA_ACTIVITY: str = "activity"
    DB_SCHEMA_BILLING: str = "billing"

    # ── Email ────────────────────────────────────────────────────────────────
    EMAIL_BACKEND: str = "auto"
    EMAIL_FROM: str = "FixMyText <dev@fixmytext.local>"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT_SECONDS: int = 10

    # ── Service identity (overrides shared defaults) ─────────────────────────
    OTEL_SERVICE_NAME: str = "fixmytext-backend"


settings = Settings()
