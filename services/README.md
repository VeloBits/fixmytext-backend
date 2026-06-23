# services/

Extracted microservices. Each service is a self-contained FastAPI app that
depends on the editable `shared/` package at `backend/shared/`.

## Services

| Directory | Owns |
|---|---|
| `services/text-svc/` | Local text-transformation tools + `tool_registry` |
| `services/ai-svc/` | Groq-backed AI text tools (translate, transliterate, tone, format) |
| `services/payments-svc/` | Razorpay subscriptions, passes, credits, webhook |
| `services/account-svc/` | User preferences, gamification, history, templates, pipelines, shares, plus auth/session (`/auth/me`, session cookie, backchannel logout, registration proxy to Keycloak) |

Keycloak OIDC integration and onboarding/profile sync — originally scoped as a
separate `identity` service — live inside `account-svc` (see `app/core/` and
`app/services/keycloak_admin.py`). No surviving monolith service remains; the
strangler-fig extraction is complete.

## Per-service layout

```
services/<name>/
├── main.py        (app entry: lifespan, middleware, router mount — at the service root)
├── app/
│   ├── api/
│   ├── core/      (service-local config, deps; thin glue to shared/)
│   ├── db/        (only if the service owns DB models)
│   └── schemas/
├── tests/
├── Dockerfile
├── pyproject.toml
└── requirements.txt
```
