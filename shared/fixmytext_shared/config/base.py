"""Cross-cutting settings mixin shared by every FixMyText service.

Service-specific Settings classes extend BaseSharedSettings and add their
own fields (DB URLs, secrets, third-party API keys). The shared base
holds observability, Redis, CORS, and rate-limit env vars - the things
that look identical across every service.
"""

import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseSharedSettings(BaseSettings):
    # Service identity (subclasses override)
    OTEL_SERVICE_NAME: str = "fixmytext-unknown"
    VERSION: str = "0.0.0"
    ENVIRONMENT: str = "development"

    # Sentry
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_RELEASE: str = ""

    # OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_EXPORTER_OTLP_HEADERS: str = ""

    # Redis (optional)
    REDIS_URL: str = ""

    # Internal service-to-service shared secret (entitlement gate, etc.).
    # Sent as the X-Internal-Secret header; verified with hmac.compare_digest.
    # Empty => internal endpoints fail closed (deny all) so a missing secret
    # never silently disables the gate.
    INTERNAL_SHARED_SECRET: str = ""

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3100,http://127.0.0.1:3100"

    # Rate limiting
    RATE_LIMIT_MAX_REQUESTS: int = 25
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Keycloak (shared across all services)
    KEYCLOAK_REALM: str = "Velobits-Dev"
    KEYCLOAK_AUDIENCE: str = "fixmytext-backend"
    # Expected token issuer (Keycloak realm URL). REQUIRED in prod - empty
    # disables issuer checks (dev only).
    KEYCLOAK_ISSUER: str = ""
    KEYCLOAK_JWKS_URL: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
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
