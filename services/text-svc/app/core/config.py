"""
Application settings for the text-svc service.

Inherits cross-cutting fields (observability, Redis, CORS, rate limits, the
internal shared secret) from ``fixmytext_shared.config.base.BaseSharedSettings``.
text-svc has no DB; it rate-limits via Redis (``rl:text``) and calls payments-svc
for the per-tool entitlement check. Auth is optional - a Keycloak JWT is decoded
only to distinguish an authenticated user from an anonymous visitor.
"""

from fixmytext_shared.config.base import BaseSharedSettings


class Settings(BaseSharedSettings):
    # ── Service identity ──────────────────────────────────────────────────────
    OTEL_SERVICE_NAME: str = "fixmytext-text-svc"
    VERSION: str = "0.1.0"

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"  # noqa: S104
    PORT: int = 8000
    DEBUG: bool = False

    # ── Optional auth (JWKS from Keycloak) ────────────────────────────────────
    # When set, a present Bearer token is decoded to identify the user; absent or
    # invalid tokens fall back to the anonymous-visitor quota.
    # KEYCLOAK_REALM, KEYCLOAK_AUDIENCE, KEYCLOAK_ISSUER, KEYCLOAK_JWKS_URL
    # are inherited from BaseSharedSettings.

    # ── Entitlement gate (payments-svc internal endpoint) ─────────────────────
    PAYMENTS_INTERNAL_URL: str = "http://payments-svc:8000"


settings = Settings()
