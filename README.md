# FixMyText — Backend

> FastAPI backend powering 200+ text transformation tools, AI writing assistance, and premium billing.

## Repository layout

Foundation for an incremental strangler-fig migration from the FastAPI
monolith into microservices
([docs/adr/0002-strangler-fig-microservices-migration.md](docs/adr/0002-strangler-fig-microservices-migration.md)):

```
backend/
├── main.py + app/              ← FastAPI monolith (intact)
├── shared/                     ← fixmytext-shared (cross-cutting utilities,
│                                  installed editable; see docs/adr/0003-shared-python-package.md)
├── gateway/kong/               ← Kong dbless config (docs/adr/0004-kong-api-gateway.md)
├── infrastructure/keycloak/    ← Keycloak realm + bootstrap (docs/adr/0001-keycloak-as-identity-provider.md)
├── services/                   ← Reserved for extracted services
└── docs/adr/                   ← Architecture Decision Records
```

Read the ADRs in numeric order for the full picture.

## Prerequisites

- Python 3.12+
- PostgreSQL 16 (or Docker)
- Groq API key (free at [console.groq.com](https://console.groq.com) — for AI tools)
- Razorpay keys (for billing features — optional for development)

## Setup

**Docker (recommended):**
```bash
cd backend
cp .env.example .env       # Fill in SECRET_KEY and optional GROQ_API_KEY
docker compose --profile dev up --build
```

Starts PostgreSQL, Redis, runs Alembic migrations, launches the API with hot
reload, and brings up Kong (gateway on `:8000`) + Keycloak (identity at
`:8080`, currently idle — no users provisioned). Frontend keeps using
`VITE_API_URL=http://localhost:8000` — Kong proxies transparently.

To skip Kong/Keycloak and hit the monolith directly (legacy dev loop):

```bash
docker compose --profile dev up backend-dev db-service redis-service migrate-dev
# Then add a temporary `ports: ["8000:8000"]` to backend-dev locally.
```

**Manual:**
```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # At minimum set DATABASE_URL + SECRET_KEY
alembic upgrade head       # Run database migrations
uvicorn main:app --reload --port 8000
```

API available at http://localhost:8000
Swagger UI: http://localhost:8000/docs
ReDoc: http://localhost:8000/redoc

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

Base URL: `http://localhost:8000/api/v1`

| Resource | Prefix | Endpoints | Description |
|----------|--------|-----------|-------------|
| Text tools | `/text/` | 200+ | Text transformations, AI tools, encoding, ciphers |
| Authentication | `/auth/` | 5 | Register, login, refresh, logout, me |
| User data | `/user-data/` | 4+ | Profile, settings, gamification stats |
| Subscriptions | `/subscription/` | 3 | Create order, webhook, status |
| Passes | `/passes/` | 2+ | Purchase and check prepaid passes |
| History | `/history/` | 2+ | Operation history (get, soft-delete) |
| Sharing | `/share/` | 2 | Create and retrieve shared results |

Health check: `GET /health` → `{"status": "ok", "version": "0.1.0"}`

## Project Structure

```
backend/
├── main.py                          # App entry: lifespan, middleware, router mount
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── router.py            # Aggregates all endpoint routers
│   │       └── endpoints/
│   │           ├── text.py          # 200+ text transformation routes
│   │           ├── auth.py          # Register, login, refresh, logout, me
│   │           ├── user_data.py     # Profile, settings, gamification
│   │           ├── subscription.py  # Razorpay billing
│   │           ├── passes.py       # Prepaid pass management
│   │           ├── history.py      # Operation history
│   │           └── share.py        # Shareable result links
│   │
│   ├── services/
│   │   ├── text_service.py         # 200+ pure text transformation functions
│   │   ├── ai_service.py           # 50+ Groq AI service classes + YAKE fallback
│   │   ├── auth_service.py         # Registration, login, password hashing
│   │   ├── pass_service.py         # Tool access control, trial limits, fingerprinting
│   │   ├── razorpay_service.py     # Payment processing, webhooks
│   │   └── region_service.py       # IP-based geolocation
│   │
│   ├── db/
│   │   ├── session.py              # Async SQLAlchemy engine + session factory
│   │   └── models/                 # 21 ORM models across 3 schemas
│   │       ├── user.py             # User (auth schema)
│   │       ├── gamification.py     # XP, streaks, achievements
│   │       ├── billing.py          # Subscriptions, passes, credits
│   │       └── ...                 # History, preferences, templates, etc.
│   │
│   ├── schemas/
│   │   ├── text.py                 # TextRequest, TextResponse, CaesarRequest, ToneRequest, etc.
│   │   ├── auth.py                 # LoginRequest, TokenResponse, UserResponse
│   │   └── ...                     # User data, billing, history schemas
│   │
│   └── core/
│       ├── config.py               # Pydantic Settings (env vars, schema names)
│       ├── security.py             # JWT creation/validation, bcrypt password hashing
│       ├── rate_limit.py           # AI endpoint rate limiter
│       └── deps.py                 # FastAPI dependencies (get_db, get_current_user, get_optional_user)
│
├── alembic/
│   ├── env.py                      # Migration environment config
│   └── versions/                   # 18 numbered migration files
│       ├── 0001_create_schemas_and_extensions.py
│       ├── 0002_create_auth_tables.py
│       └── ...
│
├── tests/                          # pytest test files
├── requirements.txt
├── Dockerfile                      # Multi-stage production build
├── Dockerfile.dev                  # Development build with hot reload
└── docker-compose.yml              # PostgreSQL + backend (dev/prod profiles)
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

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "description of change"

# Roll back one migration
alembic downgrade -1

# View migration history
alembic history
```

Note: In Docker, migrations run automatically on startup via the `migrate` service.

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
