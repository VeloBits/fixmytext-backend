"""
Application settings for the Account service.

Inherits cross-cutting fields (observability, Redis, CORS) from
``fixmytext_shared.config.base.BaseSharedSettings``. Account-specific
fields live below.
"""

from fixmytext_shared.config.base import BaseSharedSettings


class Settings(BaseSharedSettings):
    # ── Service identity ──────────────────────────────────────────────────────
    OTEL_SERVICE_NAME: str = "fixmytext-account-svc"
    VERSION: str = "0.1.0"

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"  # noqa: S104
    PORT: int = 8000
    DEBUG: bool = False

    # ── Database (same Postgres as monolith) ──────────────────────────────────
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_RECYCLE: int = 3600
    DB_SCHEMA_AUTH: str = "auth"
    DB_SCHEMA_ACTIVITY: str = "activity"
    DB_SCHEMA_BILLING: str = "billing"

    # ── Auth (JWKS from Keycloak) ─────────────────────────────────────────────
    KEYCLOAK_URL: str = ""
    # Default is now the dev realm; prod overrides via env var.
    KEYCLOAK_REALM: str = "Velobits-Dev"
    KEYCLOAK_AUDIENCE: str = "fixmytext-backend"
    # Expected token issuer (Keycloak realm URL, e.g.
    # https://auth.example.com/realms/<realm>). REQUIRED in prod — see the
    # startup assert in main.lifespan. Empty disables issuer checks (dev only).
    KEYCLOAK_ISSUER: str = ""
    KEYCLOAK_JWKS_URL: str = ""
    KEYCLOAK_ADMIN: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = ""

    # ── Session cookie (per-app, host-only, set by account-svc) ───────────────
    # Issued on successful auth so that cross-framework apps (Vite + Next.js)
    # share session state without re-authenticating.
    SESSION_COOKIE_NAME: str = "fixmytext_session"
    SESSION_COOKIE_SECRET: str = ""
    # secure=True forces the browser to send the cookie only over HTTPS.
    # Local dev runs over http://, so default is False and prod overrides.
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_MAX_AGE: int = 604800  # 7 days
    # Empty Domain attribute = host-only (intentional). The cookie scopes to
    # the exact host it was set on, preventing cross-subdomain leakage.
    SESSION_COOKIE_DOMAIN: str = ""

    # ── Share ─────────────────────────────────────────────────────────────────
    SHARE_EXPIRE_DAYS: int = 30
    MAX_SHARE_TEXT_LENGTH: int = 50_000
    FRONTEND_URL: str = "http://localhost:3000"

    # ── History ───────────────────────────────────────────────────────────────
    HISTORY_PREVIEW_MAX_LENGTH: int = 500

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # /auth/register is throttled hard per client IP — it proxies to the Keycloak
    # Admin API and can be sprayed to mass-create users, amplify verification
    # emails, or enumerate addresses (M-8).
    REGISTER_RATE_LIMIT_MAX_REQUESTS: int = 10
    REGISTER_RATE_LIMIT_WINDOW_SECONDS: int = 3600


settings = Settings()
