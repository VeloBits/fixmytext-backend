# Backend Architecture

> System overview of the FixMyText backend microservices.

## Topology

The monolith has been extracted into four standalone FastAPI services behind a
Kong API gateway (itself fronted by a Traefik edge proxy). Keycloak is the
identity provider; auth/session handling lives in `account-svc`.

```mermaid
graph TD
    Client["HTTP Client"]
    Traefik["Traefik\n(edge proxy — Host routing)"]
    Kong["Kong\n(API gateway — /api/v1/* fan-out)"]
    Account["account-svc\n(/auth · /user · /history · /share)"]
    Text["text-svc\n(/text local tools)"]
    AI["ai-svc\n(/text AI tools)"]
    Payments["payments-svc\n(/subscription · /passes)"]
    Keycloak["Keycloak\n(OIDC IdP / JWKS)"]
    DB["PostgreSQL\n(asyncpg / SQLAlchemy 2.x)"]
    Redis["Redis\n(rate limiting · session revocation)"]
    Groq["Groq API\n(llama-3.3-70b-versatile)"]
    Razorpay["Razorpay\n(payment gateway)"]

    Client --> Traefik --> Kong
    Kong --> Account
    Kong --> Text
    Kong --> AI
    Kong --> Payments
    Account -->|"JWKS verify · Admin API"| Keycloak
    Account --> DB
    Account -->|"sessions · revocation"| Redis
    Payments --> DB
    Payments -->|"billing"| Razorpay
    Text --> DB
    AI -->|"AI tool calls"| Groq
```

Each service is a self-contained FastAPI app (`main.py` at the service root)
that shares the editable `fixmytext-shared` package for cross-cutting config,
middleware, security, and observability. Within each service the request still
flows Endpoint → service/business logic → Database.

---

## Middleware Stack

Cross-cutting middleware comes from `fixmytext_shared.middleware` and is
registered per-service in each service's `main.py`. FastAPI/Starlette calls
middleware in reverse registration order — the last `add_middleware()` call
wraps outermost. For `account-svc` the effective request-processing order is:

1. **ProxyHeadersMiddleware** (outermost) — trusts `X-Forwarded-For` only from `TRUSTED_PROXY_HOSTS` so the real client IP is visible to the rate limiter (Kong is the sole trusted upstream in compose).
2. **CORSMiddleware** — validates `Origin` against the allowed-origins list, sets `Access-Control-*` response headers; `allow_credentials=True` for the session cookie.
3. **RequestLoggingMiddleware** — logs method, path, status code, latency, and the correlation ID.
4. **SecurityHeadersMiddleware** — injects `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Content-Security-Policy` on every response.
5. **CorrelationIdMiddleware** (innermost) — reads or generates a UUID correlation ID and attaches it to the request state.

---

## Tool Dispatch Pattern

All text transformation tools — both local and AI — share a unified dispatch path.

### Tool Registry

`app/core/tool_registry.py` is the single source of truth. At import time, `_register_all_tools()` populates `_TOOL_REGISTRY` — a `dict[str, ToolDefinition]`. Each entry records:

- `id` — URL-safe slug (also the route path segment, e.g. `"uppercase"`)
- `handler` — sync callable from `text_service` for `LOCAL` tools; `None` for `AI` tools
- `tool_type` — `ToolType.LOCAL` or `ToolType.AI`
- `request_model` — name of the non-standard Pydantic schema if the tool needs extra fields (e.g. `"CaesarRequest"`); `None` defaults to `TextRequest`
- `requires_auth` — `True` for all AI tools

`app/api/v1/endpoints/text.py` reads this registry at startup and generates one `POST` route per tool via `_register_routes()`, so adding a new tool requires only a registry entry.

### Local Tool Call Flow

```
POST /api/v1/text/{slug}
  → _execute_tool() in text.py
    → _enforce_tool_access()  (trial / pass check → HTTP 429 if exhausted)
    → tool.handler(request.text, *extra_params)  (pure sync function in text_service)
    → record history (for authenticated users)
    → TextResponse { original, result, operation }
```

### AI Tool Call Flow

```
POST /api/v1/text/{slug}
  → _execute_tool() in text.py
    → _enforce_tool_access()
    → ai_limiter.check()       (per-user AI rate limit)
    → ai_service.run_ai_tool(tool_id, text, *extra_args)
        → looks up tool_id in _AI_HANDLERS dict
        → _ai_transform(): tries Groq first, falls back to local function
    → record history
    → TextResponse { original, result, operation }
```

The `_AI_HANDLERS` dict in `app/services/ai_service.py` maps each AI tool slug to a 4-tuple:

```python
_AI_HANDLERS = {
    # tool_id: (prompt_key, fallback_fn, extra_fallback_args, ai_kwargs)
    "summarize": ("summarize", _summarize_fallback, (), {"temperature": 0.5, "max_tokens": 500}),
    ...
}
```

`prompt_key` references a string in `PROMPTS` (from `app/services/ai_prompts.py`). `fallback_fn` is called when Groq is unavailable.

---

## Database Layer

| Item | Detail |
|------|--------|
| ORM | SQLAlchemy 2.x (async) |
| Driver | `asyncpg` |
| Migration tool | Alembic |
| Connection factory | `app/db/session.py` — `create_async_engine` |

Models are split across three PostgreSQL schemas:

| Schema | Tables |
|--------|--------|
| `auth` | `user`, `preferences`, `user_ui_settings` |
| `activity` | `operation_history`, `user_tool_stats`, `user_tool_usage`, `visitor_usage`, `visitor_tool_usage`, `user_daily_login`, `user_discovered_tool`, `user_favorite_tool`, `user_pipeline`, `shared_result`, `template`, `user_spin_log` |
| `billing` | `billing_catalog`, `billing_subscription`, `billing_credit`, `billing_pass` |

Schema names are configured via `DB_SCHEMA_AUTH`, `DB_SCHEMA_ACTIVITY`, and `DB_SCHEMA_BILLING` in `app/core/config.py` (defaults: `auth`, `activity`, `billing`).

---

## Redis Integration

When `REDIS_URL` is set, `app/core/redis.py` opens an `asyncio`-backed connection pool at startup (FastAPI lifespan). When `REDIS_URL` is empty, services fall back to in-memory counters that do not persist across restarts or scale across workers. For `account-svc`, `REDIS_URL` is **required in production** (asserted at startup) so rate limits and session revocation hold across replicas.

Redis is used for:

- **Distributed rate limiting** — per-user/per-visitor tool counts and the per-IP registration throttle (`/auth/register`)
- **Session revocation** — `/auth/session/clear` and `/auth/backchannel-logout` add sessions to a revocation set so a stolen/logged-out cookie cannot be replayed
- **Auth cooldowns** — per-user throttle on password-reset and email-verification requests

---

## AI Service

| Item | Detail |
|------|--------|
| Provider | Groq API |
| Model | `llama-3.3-70b-versatile` (configurable via `GROQ_MODEL` in `app/core/config.py`) |
| Client | `AsyncGroq` — initialized once in FastAPI lifespan via `init_groq_client()` |
| Fallback | YAKE keyword extraction (`yake` library) for tools that have a meaningful offline fallback; `_ai_unavailable_fallback` raises HTTP 503 for tools that cannot degrade |
| Test seam | `AI_BACKEND=fake` in `.env` short-circuits all Groq calls with a deterministic stub response |
| Streaming | `stream_ai_tool()` yields token chunks via Server-Sent Events |

The `_AI_HANDLERS` registry (described above) drives all AI dispatch. Adding a new AI tool does not require a new service class — one dict entry and one prompt string are sufficient.

---

## Payments

Razorpay integration is encapsulated in two service files:

- `app/services/razorpay_service.py` — creates orders and fetches order details from the Razorpay REST API
- `app/services/payment_service.py` — verifies HMAC signatures and orchestrates the full payment confirmation flow

The billing endpoints in `app/api/v1/endpoints/subscription.py` and `passes.py` call `payment_service`. Credentials (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`) come from environment variables — never hardcoded. Set `PAYMENTS_BACKEND=fake` to use an in-memory stub during E2E tests.

---

## Request Lifecycle

### Local tool call

1. Client sends `POST /api/v1/text/uppercase` with `{"text": "hello"}` and `Authorization: Bearer <token>` + `X-Visitor-Id` headers.
2. `CorrelationIdMiddleware` stamps the request with a UUID.
3. `CORSMiddleware` validates the origin.
4. `_execute_tool()` calls `_enforce_tool_access()` — checks daily usage against the user's tier or the visitor's fingerprint. Returns HTTP 429 if exhausted.
5. `tool.handler("hello")` runs `text_service.uppercase` synchronously.
6. History is recorded for authenticated users via `record_operation_history()`.
7. `TextResponse(original="hello", result="HELLO", operation="uppercase")` is returned.

### AI tool call

Steps 1-4 are the same. Then:

5. `ai_limiter.check()` enforces the per-user AI rate limit.
6. `ai_service.run_ai_tool("summarize", text)` looks up `_AI_HANDLERS["summarize"]`, builds the system prompt from `PROMPTS["summarize"]`, and calls `_ai_transform()`.
7. `_ai_transform()` attempts `_groq_chat()` with a 35-second timeout. On failure, falls back to `_summarize_fallback(text)`.
8. History is recorded. `TextResponse` is returned.
