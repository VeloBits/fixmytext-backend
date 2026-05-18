# Kong API Gateway

Declarative dbless config for FixMyText's API gateway. Kong currently runs
only under docker-compose's `dev` profile; production deployment is TODO.

## Layout

| File | Purpose |
|---|---|
| `kong.yml` | Single-file declarative config (services, routes, plugins) |
| `plugins/` | Custom Lua plugins (empty; reserved for service-specific edge logic) |

## Reload after changes

```bash
docker compose --profile dev restart kong
# or, faster (no service restart):
curl -X POST -H "Content-Type: multipart/form-data" \
  -F "config=@gateway/kong/kong.yml" \
  http://127.0.0.1:8001/config
```

The admin API listens only on `127.0.0.1:8001` — not exposed publicly.

## Adding a new upstream service

1. Add a `services:` entry with `name`, `url`, and `routes:`.
2. Apply CORS / correlation-id plugins globally (they cascade to all services).
3. Add per-service plugins under the service's `plugins:` list.
4. Reload Kong (see above).

Placeholder routes for upcoming microservices are commented in `kong.yml`;
uncomment one at a time as each service comes online.

## Why dbless mode?

- No Postgres / Cassandra control plane required for dev.
- Config is version-controlled in this repo, not in a control-plane DB.
- Reloading config is one HTTP POST; no migrations / schema drift.

Production Kong may move to db-backed mode if multi-replica admin API
access is needed for ops, but dbless is the simplest starting point.

## Currently in scope

- **In**: monolith catch-all route, correlation-id + cors plugins,
  request-size-limiting per service.
- **TODO**: rate-limit plugin (in-app rate limit is source of truth today;
  will migrate here when a service needs per-route edge enforcement),
  per-service JWT validation plugin (requires Keycloak to be issuing
  tokens first), ACL plugin (B2B work).
