"""
Application settings loaded from environment variables via pydantic-settings.

Create a '.env' file in /backend (copy from '.env.example') to override defaults.
"""

import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    GROQ_MODEL: str = "llama-3.3-70b-versatile"  # Default Groq model for AI endpoints
    AI_BACKEND: str = (
        "auto"  # "auto" | "fake" — "fake" short-circuits Groq calls for E2E tests
    )
    PAYMENTS_BACKEND: str = "razorpay"  # "razorpay" | "fake" — "fake" stubs order create/fetch for E2E tests

    # ── Rate limiting ────────────────────────────────────────────────────────
    RATE_LIMIT_MAX_REQUESTS: int = 25  # Max requests per window (default)
    RATE_LIMIT_WINDOW_SECONDS: int = 60  # Sliding window duration in seconds
    AUTH_RATE_LIMIT_MAX: int = 50  # Higher limit for authenticated users
    VISITOR_RATE_LIMIT_MAX: int = 25  # Limit for unauthenticated visitors

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Auth / Cookies ───────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"  # "development", "staging", "production"
    COOKIE_SECURE: bool = True  # Set to False for local dev without HTTPS
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
    SHARE_EXPIRE_DAYS: int = 30  # Days before shared links expire
    MAX_SHARE_TEXT_LENGTH: int = 50_000  # Max characters for shared text

    # ── History ───────────────────────────────────────────────────────────────
    HISTORY_PREVIEW_MAX_LENGTH: int = 500  # Truncation limit for history previews

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Database pool ────────────────────────────────────────────────────────
    DB_POOL_SIZE: int = 20  # Number of persistent connections in the pool
    DB_MAX_OVERFLOW: int = 10  # Extra connections allowed beyond pool_size
    DB_POOL_RECYCLE: int = 3600  # Seconds before a connection is recycled

    # ── PostgreSQL schemas ───────────────────────────────────────────────────
    DB_SCHEMA_AUTH: str = "auth"
    DB_SCHEMA_ACTIVITY: str = "activity"
    DB_SCHEMA_BILLING: str = "billing"

    # ── Email ────────────────────────────────────────────────────────────────
    # Backend selector — "auto" picks smtp when SMTP_HOST is set, else console.
    # console just logs the message (URL + subject); smtp speaks to any SMTP
    # relay (Mailtrap Sandbox, Mailpit, etc.) for inbox previews in dev.
    EMAIL_BACKEND: str = "auto"  # "auto" | "console" | "smtp"
    EMAIL_FROM: str = "FixMyText <dev@fixmytext.local>"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True  # STARTTLS on 587; set False for plaintext dev relays
    SMTP_TIMEOUT_SECONDS: int = 10

    # ── Redis (optional — for distributed rate limiting, caching, etc.) ──────
    REDIS_URL: str = ""

    # ── Sentry ────────────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = ""  # falls back to ENVIRONMENT if empty
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_RELEASE: str = ""

    # ── OpenTelemetry / Grafana Cloud ─────────────────────────────────────────
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_EXPORTER_OTLP_HEADERS: str = ""  # comma-separated key=value pairs
    OTEL_SERVICE_NAME: str = "fixmytext-backend"

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Accepts JSON array or comma-separated string in .env
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list, accepting JSON array or comma-separated."""
        v = self.ALLOWED_ORIGINS
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return [o.strip() for o in v.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
