# fixmytext-shared

Shared Python package for FixMyText microservices. Installed as an **editable** dependency by every service via `pip install -e ./shared`.

## What's in here

| Module | Purpose |
|---|---|
| `config.base` | `BaseSharedSettings` — pydantic-settings mixin for observability, Redis, CORS, rate-limit env vars |
| `observability.sentry` | `init_sentry(settings)` + PII scrubber (`_before_send`) |
| `observability.logs` | `init_logs_otel(settings)` + `shutdown_logs_otel()` (OTel logs → Loki via OTLP HTTP) |
| `observability.sanitize` | `LogSanitizationFilter` (control-char strip) + `PiiRedactionFilter` (keyword redaction) |
| `middleware.correlation_id` | `CorrelationIdMiddleware` — sets/echoes `X-Request-ID` |
| `middleware.security_headers` | `SecurityHeadersMiddleware` — adds CSP, HSTS, X-Frame-Options, etc. |
| `middleware.request_logging` | `RequestLoggingMiddleware` — logs method, path, status, duration |
| `rate_limit.memory` | `InMemoryRateLimiter` — single-instance fallback |
| `rate_limit.redis_limiter` | `RedisRateLimiter` — sliding window over Redis sorted sets |
| `rate_limit.factory` | `create_limiter()` — picks Redis when configured, else in-memory |
| `security.jwt` | `verify_jwt(token, *, algorithm=None)` — dispatcher to HS256 or JWKS adapter |
| `security.hs256` | HS256 adapter (legacy fallback — not used in normal operation) |
| `security.jwks` | RS256 + JWKS adapter — active production path for Keycloak-issued tokens |
| `security.claims` | `ClaimSchema` — typed JWT payload (B2C now, optional `org_id` for B2B later) |
| `schemas.errors` | `ErrorResponse`, `HTTPErrorEnvelope` |
| `exceptions.http` | `AuthError`, `RateLimitError`, `ConfigError` |

## Install (from a service)

Each service's `requirements.txt` adds:

```
-e ../shared          # relative path; compose mounts both sibling dirs
```

Or in `pyproject.toml`:

```toml
dependencies = ["fixmytext-shared @ file:///app/shared"]
```

## Tests

```bash
pip install -e ./shared[test]
pytest shared/tests -v
```

Smoke tests cover sanitization, rate-limiting, HS256 round-trip, and JWKS adapter against a static in-test RSA keypair.

## Design notes

- **No business logic.** This package is cross-cutting concerns only — observability, middleware, rate limit, JWT. Business utilities live in services.
- **No global state.** Functions take `settings` as argument. `init_*()` is idempotent; safe to call multiple times.
- **JWT dispatcher.** `verify_jwt()` reads `JWT_ALGORITHM` env var (default `RS256`) and routes to the right adapter. RS256/JWKS is the production path (Keycloak tokens). HS256 is the legacy fallback; no service uses it in normal operation.
