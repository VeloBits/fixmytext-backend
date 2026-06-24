# FixMyText — Backend

> FastAPI backend powering 200+ text transformation tools, AI writing assistance, and premium billing.

## Repository layout

Result of an incremental strangler-fig migration from the FastAPI
monolith into microservices
([docs/adr/0002-strangler-fig-microservices-migration.md](docs/adr/0002-strangler-fig-microservices-migration.md)).
The monolith has been extracted into four standalone FastAPI services
behind a Kong gateway:

```
backend/
├── services/                   ← Extracted FastAPI microservices
│   ├── account-svc/            ← preferences, gamification, history, templates, pipelines, shares, auth/session
│   ├── text-svc/               ← local text-transformation tools + tool_registry
│   ├── ai-svc/                 ← Groq-backed AI text tools
│   └── payments-svc/           ← Razorpay subscriptions, passes, credits, webhooks
├── shared/                     ← fixmytext-shared (cross-cutting utilities,
│                                  installed editable; see docs/adr/0003-shared-python-package.md)
├── gateway/
│   ├── kong/                   ← Kong dbless config (docs/adr/0004-kong-api-gateway.md)
│   └── traefik/                ← Traefik edge proxy (Host-header routing)
├── infrastructure/keycloak/    ← Keycloak realm + bootstrap (docs/adr/0001-keycloak-as-identity-provider.md)
└── docs/adr/                   ← Architecture Decision Records
```

Read the ADRs in numeric order for the full picture.

## Prerequisites

- Python 3.12+
- PostgreSQL 16 (or Docker)
- Groq API key (free at [console.groq.com](https://console.groq.com) — for AI tools)
- Razorpay keys (for billing features — optional for development)

## Local development with VeloBits subdomains

The backend runs behind **Traefik** (edge reverse proxy) which routes
by `Host` header to the right container. Local dev mirrors production
exactly — only DNS source changes (`/etc/hosts` here, real DNS in production).

### One-time `/etc/hosts` setup

Add these entries (requires sudo):

```bash
sudo tee -a /etc/hosts <<EOF
127.0.0.1 auth-dev.velobits.dev
127.0.0.1 api-dev.velobits.dev
127.0.0.1 develop-fixmytext.velobits.dev
EOF
```

### Subdomain map (dev)

| URL | Container | Purpose |
|---|---|---|
| `http://auth-dev.velobits.dev` | `keycloak-dev` | Keycloak (Velobits-Dev realm) |
| `http://api-dev.velobits.dev` | `kong` | API gateway → backend microservices |
| `http://develop-fixmytext.velobits.dev` | (frontend dev container, run separately) | FixMyText dev frontend |
| `http://127.0.0.1:8090` | `traefik` | Traefik dashboard (localhost-only) |

## Setup

**Docker (recommended):**
```bash
cd backend
cp .env.example .env       # Fill in SESSION_COOKIE_SECRET + KEYCLOAK_DEV_* + GROQ_API_KEY
docker compose --profile dev up --build
```

Starts PostgreSQL (product DBs), Redis, runs Alembic migrations, launches the
backend microservices, brings up Kong (API gateway behind Traefik) +
Keycloak-Dev (Velobits-Dev realm) + Traefik (edge proxy on `:80`).

To skip Kong/Keycloak and hit the monolith directly (legacy dev loop):

```bash
docker compose --profile dev up backend-dev db-service redis-service migrate-dev
# Then add a temporary `ports: ["8000:8000"]` to backend-dev locally.
```

### API docs (Swagger) in dev

`docker-compose.override.yml` publishes each service on a loopback host port so
its interactive docs are reachable directly (Kong on `:8000` only routes
`/api/v1/*`, not `/docs`). The override is auto-merged by `docker compose` — no
extra flags needed. After `docker compose --profile dev up`:

| Service | Swagger UI | ReDoc | OpenAPI schema |
|---------|------------|-------|----------------|
| ai-svc | http://localhost:8011/docs | http://localhost:8011/redoc | http://localhost:8011/openapi.json |
| text-svc | http://localhost:8012/docs | http://localhost:8012/redoc | http://localhost:8012/openapi.json |
| payments-svc | http://localhost:8013/docs | http://localhost:8013/redoc | http://localhost:8013/openapi.json |
| account-svc | http://localhost:8014/docs | http://localhost:8014/redoc | http://localhost:8014/openapi.json |

Docs are served only when `ENVIRONMENT=development` (the default); they return
404 in prod-like environments regardless of the port mapping.

**Manual (single service, e.g. account-svc):**
```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e shared                         # editable fixmytext-shared
pip install -r services/account-svc/requirements.txt
cp .env.example .env       # At minimum set DATABASE_URL + SESSION_COOKIE_SECRET
alembic upgrade head       # Run database migrations
cd services/account-svc && uvicorn main:app --reload --port 8003
```

Each service binds its own port (account-svc defaults to 8003). When the
service runs in `development`, Swagger UI is at `/docs` and ReDoc at
`/redoc`; both are disabled outside development.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string (`postgresql+asyncpg://user:pass@host:port/db`) |
| `POSTGRES_PASSWORD` | Docker only | — | Password for the Docker PostgreSQL container |
| `SECRET_KEY` | Yes | — | JWT signing key (generate: `openssl rand -hex 32`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime in days |
| `GROQ_API_KEY` | For AI tools | — | Groq API key for Llama 3.3 70B |
| `RAZORPAY_KEY_ID` | For billing | — | Razorpay key ID |
| `RAZORPAY_KEY_SECRET` | For billing | — | Razorpay key secret |
| `RAZORPAY_WEBHOOK_SECRET` | For billing | — | Razorpay webhook verification secret |
| `ALLOWED_ORIGINS` | No | `["http://localhost:3000"]` | CORS allowed origins (JSON array string) |
| `FREE_USES_PER_TOOL_PER_DAY` | No | `3` | Daily free tool uses per visitor |
| `DAILY_LOGIN_BONUS` | No | `1` | XP bonus for daily login |
| `FRONTEND_URL` | No | `http://localhost:3000` | Frontend URL for CORS and redirects |
| `HOST` | No | `0.0.0.0` | Server bind host |
| `PORT` | No | `8000` | Server port |
| `DEBUG` | No | `false` | Enable debug mode |

## API Structure

All routes are exposed behind the Kong gateway under the shared `/api/v1`
base path; Kong fans each prefix out to the owning service.

| Resource | Prefix | Service | Description |
|----------|--------|---------|-------------|
| Text tools | `/text/` | `text-svc` / `ai-svc` | Text transformations, AI tools, encoding, ciphers |
| Authentication / session | `/auth/` | `account-svc` | `/auth/me`, session clear, registration, backchannel logout |
| User data | `/user/` | `account-svc` | Preferences, gamification, templates, ui-settings, favorites, tool-stats, pipelines, discovered-tools, spin-history |
| Subscriptions | `/subscription/` | `payments-svc` | Create order, webhook, status |
| Passes | `/passes/` | `payments-svc` | Purchase and check prepaid passes |
| History | `/history/` | `account-svc` | Operation history (list, record, stats, soft-delete) |
| Sharing | `/share/` | `account-svc` | Create and retrieve shared results |

Each service exposes its own health check: `GET /health` →
`{"status": "ok", "version": "0.1.0", "service": "<name>"}`, plus
`GET /health/ready` for DB-connectivity readiness probes.

## Project Structure

Each service is a self-contained FastAPI app sharing the editable
`fixmytext-shared` package. The `account-svc` layout is representative:

```
backend/
├── services/
│   ├── account-svc/
│   │   ├── main.py                     # App entry: lifespan, prod config asserts, middleware, router mount
│   │   ├── app/
│   │   │   ├── api/v1/
│   │   │   │   ├── router.py           # Aggregates endpoint routers
│   │   │   │   └── endpoints/
│   │   │   │       ├── auth.py         # /auth/me, session clear, backchannel logout
│   │   │   │       ├── auth_register.py# Registration proxy to Keycloak Admin API
│   │   │   │       ├── user_data.py    # Preferences, gamification, templates, favorites, pipelines, …
│   │   │   │       ├── history.py      # Operation history
│   │   │   │       └── share.py        # Shareable result links
│   │   │   ├── db/                     # Async SQLAlchemy session + ORM models
│   │   │   ├── schemas/                # Pydantic request/response models
│   │   │   └── core/                   # config.py, deps.py, redis.py, session_cookie.py, keycloak_admin.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── requirements.txt
│   ├── text-svc/                       # local text tools + tool_registry
│   ├── ai-svc/                         # Groq-backed AI tools + YAKE fallback
│   └── payments-svc/                   # Razorpay subscriptions, passes, credits, webhooks
│
├── shared/fixmytext_shared/            # cross-cutting: config, middleware, security, observability
├── gateway/{kong,traefik}/            # Kong dbless config + Traefik edge proxy
├── infrastructure/keycloak/           # realm exports, bootstrap.sh, themes
├── services/<svc>/migrations/         # per-service Alembic chains (account → payments)
├── Dockerfile.migrate                 # image that runs both migration chains in order
└── docker-compose.yml                 # full stack: Postgres, Redis, services, Kong, Keycloak, Traefik
```

## Architecture

### Layered Design

```
Request → Endpoint (app/api/) → Service (app/services/) → Database (app/db/)
                                       ↓
                              External APIs (Groq, Razorpay)
```

- **Endpoints** handle HTTP concerns: request parsing, auth, rate limiting, response formatting
- **Services** contain all business logic: text transforms, AI calls, auth, billing
- **Models** define the database schema via SQLAlchemy ORM
- **Schemas** define request/response shapes via Pydantic

### Key Patterns

- **`_local_endpoint()`** — Helper for non-AI text tools: enforces access, calls transform, records history
- **`_ai_endpoint()`** — Helper for AI tools: rate limits, calls AI service class, records history
- **`_enforce_tool_access()`** — Checks visitor/user trial limits before processing
- **`ai_limiter.check()`** — Per-user rate limiting for AI endpoints

### Request/Response Models

```python
# Standard text request
class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)

# Standard text response
class TextResponse(BaseModel):
    original: str
    result: str
    operation: str

# Specialized requests
class CaesarRequest(BaseModel):
    text: str
    shift: int = Field(default=3, ge=1, le=25)

class ToneRequest(BaseModel):
    text: str
    tone: Literal["formal", "casual", "friendly"]

class FormatRequest(BaseModel):
    text: str
    format: Literal["paragraph", "bullets", "numbered", "qna", "table", "tldr", "headings"]
```

## Database

### Three PostgreSQL Schemas

**`auth` schema:**
| Model | Description |
|-------|-------------|
| `users` | Core accounts: email, hashed password, display name, referral code, region |

**`activity` schema:**
| Model | Description |
|-------|-------------|
| `operation_history` | Past transformations (tool_id, input/output preview, soft delete) |
| `user_gamification` | XP, streaks, achievements (JSONB), daily quests |
| `user_preferences` | User settings and preferences |
| `user_ui_settings` | UI config (theme, sidebar state) |
| `user_tool_stats` | Per-tool usage statistics |
| `user_daily_login` | Daily login tracking |
| `user_favorite_tool` | Bookmarked tools |
| `user_discovered_tool` | Tools the user has tried |
| `user_spin_log` | Lucky spin history |
| `user_pipeline` | Chained operation pipelines |
| `visitor_usage` | Anonymous visitor daily limits |
| `visitor_tool_usage` | Visitor per-tool usage |
| `template` | Saved operation templates |
| `shared_result` | Public shareable links |

**`billing` schema:**
| Model | Description |
|-------|-------------|
| `subscription` | User tier (free/pro) with Razorpay subscription ID |
| `payment_event` | Razorpay webhook events |
| `billing_pass` | Pass product catalog |
| `billing_user_pass` | User's purchased passes |
| `billing_user_credit` | In-app credit balance |
| `billing_catalog` | Pricing catalog |

### Key Features
- **Async SQLAlchemy** with asyncpg driver for non-blocking queries
- **UUID primary keys** via `gen_random_uuid()`
- **Timezone-aware timestamps** on all models
- **JSONB columns** for achievements and quest data
- **Soft deletes** on operation_history and shared_results
- **pgvector extension** installed for future vector embedding support

## Migrations

Each service owns its own Alembic chain under `services/<svc>/migrations/` with its
own version table. On a fresh DB, **account-svc must run before payments-svc**
(billing/usage tables keep cross-schema FKs into `auth.users`). See
[CONTRIBUTING.md §9](CONTRIBUTING.md) for ownership details.

```bash
# Apply all pending migrations (account first, then payments)
alembic -c services/account-svc/migrations/alembic.ini upgrade head
alembic -c services/payments-svc/migrations/alembic.ini upgrade head

# Create a new migration after model changes (per owning service)
alembic -c services/<svc>/migrations/alembic.ini revision --autogenerate -m "description"

# Roll back one migration / view history (per service)
alembic -c services/<svc>/migrations/alembic.ini downgrade -1
alembic -c services/<svc>/migrations/alembic.ini history
```

Note: In Docker, migrations run automatically on startup via the `migrate-dev`
service, which runs both chains in order.

## Adding a New Tool

See [Adding a Tool Guide](../docs/adding-a-tool.md) for the full walkthrough.

**Quick summary for backend-only changes:**

1. Add function to `app/services/text_service.py` (pure function, `str → str`)
2. Add endpoint to `app/api/v1/endpoints/text.py` using `_local_endpoint()` helper
3. For AI tools: add service class to `app/services/ai_service.py`, use `_ai_endpoint()` helper

## Running Tests

```bash
# All tests
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing

# Specific file
pytest tests/test_text_service.py -v

# Only failing tests
pytest --lf
```

## Pre-commit Hooks

Run `ruff format`, `ruff check --fix`, a `pytest -q tests/core` smoke, plus
detect-secrets and standard hygiene checks before each commit.

```bash
pip install pre-commit         # one-time
pre-commit install             # installs the git hook into .git/hooks/pre-commit
pre-commit run --all-files     # optional: run against the whole tree once
```

`pytest` must resolve to the project venv (so `tests/core` imports work) —
activate `.venv` before committing, or run commits from a shell where it's on
PATH. The frontend's Husky hook lives in `frontend/.git` and is unaffected.
