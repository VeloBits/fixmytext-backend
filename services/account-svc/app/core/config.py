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

    # ── Auth (JWKS / Admin API) ───────────────────────────────────────────────
    # KEYCLOAK_REALM, KEYCLOAK_AUDIENCE, KEYCLOAK_ISSUER, KEYCLOAK_JWKS_URL
    # are inherited from BaseSharedSettings.
    KEYCLOAK_URL: str = ""  # Admin API base (account-svc only)
    KEYCLOAK_ADMIN: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = ""
    # OIDC client ID used in the verification-email link so Keycloak generates
    # a redirect back to the correct frontend app (not the default account console).
    KEYCLOAK_CLIENT_ID: str = ""
    # Dedicated service account for Keycloak Admin API calls. When both are set,
    # keycloak_admin.py uses client_credentials grant in the product realm instead
    # of the master-realm admin-cli password grant. Created by bootstrap.sh.
    KEYCLOAK_SERVICE_ACCOUNT_ID: str = ""
    KEYCLOAK_SERVICE_ACCOUNT_SECRET: str = ""

    # ── Session cookie (per-app, host-only, set by account-svc) ───────────────
    # Issued on successful auth so that cross-framework apps (Vite + Next.js)
    # share session state without re-authenticating.
    SESSION_COOKIE_NAME: str = "fixmytext_session"
    SESSION_COOKIE_SECRET: str = ""
    # secure=True forces the browser to send the cookie only over HTTPS.
    # Default is True (safe). Local dev over http:// must set
    # SESSION_COOKIE_SECURE=false explicitly in .env.
    SESSION_COOKIE_SECURE: bool = True
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
    # /auth/resend-verification is throttled per user - each call makes Keycloak
    # send a real verification email, so it can be sprayed for email amplification.
    RESEND_VERIFICATION_RATE_LIMIT_MAX_REQUESTS: int = 10
    RESEND_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS: int = 3600

    # ── Backchannel logout ────────────────────────────────────────────────────
    # Optional shared secret for the /auth/backchannel-logout endpoint.  When
    # set, Keycloak must include this value in the X-Backchannel-Secret header
    # (configured in the realm's backchannel logout settings).  Prevents
    # arbitrary callers from replaying logout tokens to revoke other users'
    # sessions.  Leave empty to skip this check (default, development-friendly).
    BACKCHANNEL_SECRET: str = ""

    # ── Reverse proxy trust ───────────────────────────────────────────────────
    # Hosts/CIDRs whose X-Forwarded-For header is trusted by ProxyHeadersMiddleware.
    # "*" trusts every upstream - safe only in local compose where Kong is the
    # sole network entry point. Production MUST set this to the Kong container's
    # internal subnet (e.g. "10.0.0.0/8") so IP spoofing via injected XFF headers
    # cannot bypass the rate limiter. Enforced by the startup assert in main.py.
    TRUSTED_PROXY_HOSTS: str = "*"


settings = Settings()
