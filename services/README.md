# services/

Reserved for extracted microservices. Each service is a self-contained
FastAPI app that depends on the editable `shared/` package at
`backend/shared/`.

## Planned services

| Directory | Owns |
|---|---|
| `services/identity/` | OIDC integration with Keycloak; onboarding / profile sync |
| `services/text-svc/` | Local text-transformation tools + `tool_registry` |
| `services/ai-svc/` | Groq-backed AI text tools (translate, transliterate, tone, format) |
| `services/payments-svc/` | Razorpay subscriptions, passes, credits, webhook |
| `services/account-svc/` | User preferences, gamification, history, templates, pipelines, shares |
| `services/monolith/` | TODO — surviving monolith routes during the strangler-fig migration |

## Per-service layout (target)

```
services/<name>/
├── app/
│   ├── api/
│   ├── core/      (service-local config, deps; thin glue to shared/)
│   ├── db/        (only if the service owns DB models)
│   ├── schemas/
│   └── main.py
├── tests/
├── alembic/       (per-service migrations)
├── Dockerfile
├── pyproject.toml
└── requirements.txt
```

This directory is intentionally empty for now — services will be added as
each extraction lands.
