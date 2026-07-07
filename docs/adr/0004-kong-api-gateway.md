# ADR 0004: Kong as API gateway

- **Status**: Accepted (2026-05-18)

## Context

When the monolith splits into services, the frontend needs a single entry
point for `/api/v1/*` traffic. Without a gateway, either:
1. Frontend learns about all service URLs (`VITE_AUTH_URL`,
   `VITE_TEXT_URL`, etc.) — 7 RTK Query slices each need their own base,
   per-environment env vars multiply.
2. Or one service becomes a reverse-proxy aggregator — couples deployment
   of services.

We need a path-prefix-dispatch gateway: `/api/v1/auth/*` → identity
provider, `/api/v1/text/*` → text-svc, etc. The frontend keeps a single
`VITE_API_URL`.

## Decision

Use **Kong 3.x** in **dbless mode**, declared via a single `kong.yml`
file at `backend/gateway/kong/kong.yml`.

- **Dbless mode**: no Postgres/Cassandra control plane in dev. Config is
  reloaded by re-applying the YAML.
- **Single source of routing truth**: every `/api/v1/<service>/*` path
  is declared in `kong.yml`. New service = add one entry + reload Kong.
- **Plugins**: `correlation-id` (echoes `X-Request-ID` downstream), `cors`
  (origins for localhost dev; production origins via env), `request-size-limiting`
  (1 MB cap per request).
- **Current scope**: one service (monolith) and a catch-all `/api/v1` +
  `/health` route. Placeholders for `identity-svc`, `ai-svc`, `text-svc`,
  `payments-svc`, `account-svc` are commented in for future extraction PRs.

## Why Kong (not nginx, Traefik, Caddy)

| Option | Rejected because |
|---|---|
| nginx | Plain reverse proxy. CORS, correlation-ID, rate-limit, ACL all become custom Lua / NGINX modules. Works, but every plugin is a snowflake. |
| Traefik | Container-label-based routing is convenient but couples config to the deployment manifest. Less mature plugin ecosystem than Kong. |
| Caddy | Minimal but lacks the plugin breadth Kong has out of the box (correlation-ID, JWT verification, ACL). |

Kong's plugin ecosystem (free plugins: `correlation-id`, `cors`,
`rate-limiting`, `jwt`, `acl`, `request-size-limiting`) replicates the
monolith's existing middleware behaviour with zero custom code. Per-service
edge policies (different rate limits for AI vs. text, JWT validation at
the edge) become config rather than code.

## Consequences

**Positive:**
- Adding a new service is one block of YAML.
- Frontend continues using `VITE_API_URL=http://localhost:8000` (Kong).
  Zero frontend code changes when services come online.
- Plugins can replace monolith middleware as services migrate
  (e.g. CORS moves from monolith → Kong with the auth cutover; rate-limit
  moves when a service splits out).

**Negative:**
- One more container in dev (`fixmytext-kong`, ~150 MB memory).
- Mismatch potential between Kong's `kong.yml` and what the services
  actually expose. Mitigated: every new service PR adds a CI step
  that validates the gateway config.

**Neutral:**
- Production deployment may move to Kong's db-backed mode if multi-replica
  admin API access is needed for ops. Dbless is the simplest starting point.
- Kong's CVE surface is monitored by Trivy in CI (`--ignore-unfixed`
  policy already in place).

## Rate-limit plugin: deferred

In-app rate limiting (`fixmytext_shared.rate_limit`) is source of truth
today. Migrating to Kong's `rate-limiting` plugin is TODO — the AI quota
check has the most to gain from edge enforcement (early rejection before
a request even reaches the service).
