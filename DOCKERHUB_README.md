# FixMyText Backend

> FastAPI backend powering 200+ text transformation tools, AI writing assistance, JWT auth, gamification, and Razorpay billing.

---

## Quick start

```bash
docker run -d \
  --name fixmytext-backend \
  -p 8000:8000 \
  -e DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/fixmytext' \
  -e SECRET_KEY='your-secret-key-min-32-chars' \
  velobits/fixmytext-backend:latest
```

Generate a secure secret key:
```bash
openssl rand -hex 32
```

API: `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`  
ReDoc: `http://localhost:8000/redoc`

---

## Docker Compose

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: fixmytext
      POSTGRES_PASSWORD: yourpassword
      POSTGRES_DB: fixmytext
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    image: velobits/fixmytext-backend:latest
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://fixmytext:yourpassword@db:5432/fixmytext
      SECRET_KEY: your-secret-key-min-32-chars
      GROQ_API_KEY: your-groq-api-key        # optional, for AI tools
      ALLOWED_ORIGINS: '["http://localhost:3000"]'
    depends_on:
      - db

volumes:
  pgdata:
```

> Alembic migrations run automatically on container start.

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string (`postgresql+asyncpg://user:pass@host:port/db`) |
| `SECRET_KEY` | Yes | — | JWT signing key — min 32 chars (`openssl rand -hex 32`) |
| `GROQ_API_KEY` | For AI tools | — | Groq API key for Llama 3.3 70B |
| `RAZORPAY_KEY_ID` | For billing | — | Razorpay key ID |
| `RAZORPAY_KEY_SECRET` | For billing | — | Razorpay key secret |
| `RAZORPAY_WEBHOOK_SECRET` | For billing | — | Razorpay webhook verification secret |
| `ALLOWED_ORIGINS` | No | `["http://localhost:3000"]` | CORS allowed origins (JSON array string) |
| `FRONTEND_URL` | No | `http://localhost:3000` | Frontend URL for CORS and redirects |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime in days |
| `FREE_USES_PER_TOOL_PER_DAY` | No | `3` | Daily free tool uses per visitor |
| `PORT` | No | `8000` | Server port |
| `DEBUG` | No | `false` | Enable debug mode |

---

## API

Base URL: `/api/v1`

| Resource | Prefix | Description |
|---|---|---|
| Text tools | `/text/` | 200+ transformations — case, encoding, ciphers, AI writing, hashing |
| Authentication | `/auth/` | Register, login, refresh, logout |
| User data | `/user-data/` | Profile, settings, gamification stats |
| Subscriptions | `/subscription/` | Razorpay order creation and webhook |
| Passes | `/passes/` | Prepaid usage passes |
| History | `/history/` | Operation history |
| Sharing | `/share/` | Public shareable result links |

---

## Health checks

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness — returns `{"status":"ok","version":"<version>"}` |
| `GET /health/ready` | Readiness — checks database connectivity |

---

## Image tags

| Tag | Points to |
|---|---|
| `latest` | Latest stable release |
| `1`, `1.0`, `1.0.0` | Semantic version — major / minor / patch |
| `sha-<commit>` | Pinned to a specific commit |

Pre-release tags (e.g. `1.0.0-beta.1`) are published but do not move `latest`.

---

## Requirements

- **PostgreSQL 16** with the `pgvector` extension
- Alembic migrations run automatically on container start — no manual setup needed

---

## Architectures

`linux/amd64` · `linux/arm64`

---

## Source

**GitHub:** https://github.com/VeloBits/fixmytext-backend
