"""
Application settings for the AI service.

Inherits cross-cutting fields (observability, Redis, CORS, rate limits)
from ``fixmytext_shared.config.base.BaseSharedSettings``.  AI-specific
fields (Groq, Keycloak JWKS) live below.
"""

from fixmytext_shared.config.base import BaseSharedSettings


class Settings(BaseSharedSettings):
    # ── Service identity ──────────────────────────────────────────────────────
    OTEL_SERVICE_NAME: str = "fixmytext-ai-svc"
    VERSION: str = "0.1.0"

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"  # noqa: S104
    PORT: int = 8000
    DEBUG: bool = False

    # ── AI / Groq ─────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    AI_BACKEND: str = "auto"

    # ── Auth (JWKS from Keycloak) ─────────────────────────────────────────────
    KEYCLOAK_URL: str = ""
    KEYCLOAK_REALM: str = "fixmytext"
    KEYCLOAK_AUDIENCE: str = "fixmytext-backend"
    KEYCLOAK_JWKS_URL: str = ""

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_MAX_REQUESTS: int = 25
    RATE_LIMIT_WINDOW_SECONDS: int = 60


settings = Settings()
