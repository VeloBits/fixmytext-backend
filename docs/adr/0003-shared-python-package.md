# ADR 0003: Shared Python package (`fixmytext-shared`)

- **Status**: Accepted (2026-05-18)

## Context

Every extracted service will need:
- Sentry init + PII scrubber
- OTel logs init (OTLP HTTP → Loki)
- Log sanitisation + PII redaction filters
- Correlation-ID / security-headers / request-logging middleware
- Redis sliding-window rate limiter (+ in-memory fallback)
- JWT verification (HS256 today; RS256/JWKS once Keycloak is live)
- A `ClaimSchema` dataclass for typed access to JWT payloads
- Cross-cutting pydantic-settings fields (Sentry / OTel / Redis / CORS)

Without a shared location, every service either copies these from the
monolith (drift on every bug fix) or imports them from a vendored
dependency. We need a single source of truth that:

1. Is reusable from every service.
2. Is version-controlled in the same git repo (no separate publish step).
3. Doesn't require a private PyPI server.
4. Lets us change the shared code in one place and pick it up
   automatically in every service.

## Decision

Create an **editable Python package** at `backend/shared/`, installable as
`fixmytext-shared` via `pip install -e ./shared` from any service.

### Layout

```
backend/shared/
├── pyproject.toml                 # name = fixmytext-shared
├── README.md
├── fixmytext_shared/
│   ├── config/base.py             # BaseSharedSettings (pydantic-settings mixin)
│   ├── observability/             # sentry, logs, sanitize
│   ├── middleware/                # corr-id, security-headers, request-logging
│   ├── rate_limit/                # memory, redis, factory
│   ├── security/                  # jwt, hs256, jwks, claims
│   ├── schemas/                   # error envelopes
│   └── exceptions/                # AuthError, RateLimitError, ConfigError
└── tests/                         # 32 smoke tests
```

### How services consume it

Each service's `requirements.txt`:

```
-e ../shared
```

(or absolute `-e /app/shared` inside containers). The editable install
means any change in `backend/shared/fixmytext_shared/` is picked up at the
next import without a re-install — fast iteration.

### What stays in services vs. moves to shared

| Stays in services | Moves to shared |
|---|---|
| Business logic (auth flow, AI tool dispatch, Razorpay glue) | Cross-cutting infra (observability, middleware, rate-limit, JWT verify) |
| DB models | Pydantic Settings *mixin* (each service has its own Settings class extending it) |
| API routes | None — services own their routes |
| Service-specific configs (Groq, Razorpay, SMTP) | Sentry / OTel / Redis / CORS config fields |

Rule of thumb: **infrastructure goes in shared; product logic stays in services.**

## Alternatives considered

| Option | Rejected because |
|---|---|
| Copy-paste between services | Drift on every change — a bug in PII scrubbing fixed in one service silently leaves others vulnerable. |
| Git submodule | Adds a separate repo to manage; sub-modules are notoriously easy to forget to update. |
| Private PyPI | Requires a server (DevPI, Nexus, GitHub Packages); release versioning becomes another thing to babysit; iteration speed drops. |
| Vendored copy with periodic sync | Worse drift than submodule — needs a manual sync script. |

The editable install is the simplest thing that works for a monorepo with
a single dev.

## How the monolith adopts it

The monolith's `app/core/{sentry, observability_logs, sanitize,
rate_limit}.py` files become **thin re-export shims** that:
- Import the real implementation from `fixmytext_shared`
- Pre-bind the monolith's `settings` instance where the shared function
  expects one as an argument
- Re-export private symbols (e.g. `_before_send`, `_PII_KEYS`) that
  existing tests import directly

This keeps every existing call site working without code changes. The
shims will be deleted when the monolith physically moves to
`services/monolith/` and import paths change anyway.

## Consequences

**Positive:**
- Single source of truth for cross-cutting infra.
- New service in the future = `pip install -e ../shared` + write
  business logic. No copy-pasted boilerplate.
- Bug fixes propagate automatically (editable install picks up changes).

**Negative:**
- Docker build context must include `shared/`. Mitigated: build context
  is `backend/` for every service Dockerfile.
- The `-e ./shared` entry in `requirements.txt` is a relative path — works
  in the monorepo but breaks if a service is ever published as a wheel
  to PyPI. Mitigated: services are never wheel-published; they're
  always deployed as Docker images.

**Neutral:**
- `BaseSharedSettings` defines defaults; service-specific `Settings`
  subclasses override (e.g. `OTEL_SERVICE_NAME`).
- Shared package version (`0.1.0` today) will be bumped when breaking
  changes land. SemVer applies internally even though it's not published.
