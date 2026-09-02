# Octopus Deployment Runbook — fixmytext-backend

**Day-to-day operations**: deploying, promoting, rolling back, rotating secrets,
and diagnosing a deploy that went wrong.

For the **one-time setup** — Octopus instance, environments, lifecycles, the VM
and Tentacle, the project, its channels and process, the variable tables, DNS,
and the managed database — see [octopus-setup.md](octopus-setup.md).

---

## The shape of a deploy

```
GitHub Actions ("Deploy via Octopus", any branch, manual trigger)
  │  CI gate → stage compose + octopus + services/ + shared/ → fixmytext-backend.<version>.zip
  ▼
Octopus Cloud            release + channel + lifecycle (instance shared with velobits-infra)
  │  polling Tentacle — VM dials OUT to Octopus :10943; no inbound ports
  ▼
Oracle Ubuntu VM (Tentacle target, roles: velobits-docker-host)
     extract package → render .env from sensitive variables → octopus/deploy.sh
     ├─ Development: docker-compose.yml + octopus/docker-compose.deploy.yml
     │    --profile dev, Kong exposed to Traefik as `kong`
     └─ Production:  docker-compose-prod.yml
          Kong exposed as `kong-prod`, no published host ports at all

     images:   BUILT ON THE VM from packaged sources (arm64 target)
     database: remote managed Postgres, separate database per environment —
               the VM runs no database container
     redis:    on the VM (ephemeral counters + the arq job queue)
```

Traefik routes `api-dev.fixmytext.velobits.dev` / `api.fixmytext.velobits.dev`
to this stack's Kong. Those routers live in the infra repo
(`traefik/rules/fixmytext-dev.yml`, `traefik/rules-prod/fixmytext-prod.yml`); the
hostname convention itself is in `velobits-infra/traefik/README.md`.

Files involved:

- [.github/workflows/deploy-octopus.yml](../.github/workflows/deploy-octopus.yml) — the manual pipeline
- [octopus/deploy.sh](../octopus/deploy.sh) — runs on the VM per deploy; picks the stack from `DEPLOY_ENV`
- [octopus/env.dev.template](../octopus/env.dev.template) / [octopus/env.prod.template](../octopus/env.prod.template) — Octopus-variable → `.env` mapping
- [octopus/docker-compose.deploy.yml](../octopus/docker-compose.deploy.yml) — deploy-time override for the dev stack
- [docker-compose-prod.yml](../docker-compose-prod.yml) — the production stack
- [scripts/check-env-templates.sh](../scripts/check-env-templates.sh) — CI guard over the templates

**Runtime dependency:** the velobits-infra stack must be up. Every service here
fetches JWKS from Keycloak over `velobits-proxy-net`, and Traefik terminates TLS
for the API hostname. `deploy.sh` creates the network if missing so a first
deploy cannot hard-fail on ordering, but the API 502s until Traefik is running
and tokens cannot be validated until Keycloak is. The two *infra* stacks cannot
run side by side (both own :80/:443), and each backend stack is pinned to its
matching identity container — dev expects `keycloak-dev`, prod expects
`velobits-auth` — so pair dev with dev and prod with prod. The two *backend*
stacks do not collide with each other.

---

## Deploy any branch to Development

1. Push your branch and let **Backend Test & Build** go green. The deploy
   workflow reads the latest conclusion for that exact commit and refuses to run
   otherwise (H-7); a never-run CI reports `missing` and is treated as a
   failure, not a skip.
2. GitHub → Actions → **Deploy via Octopus** → *Run workflow* → pick the branch
   → Run. (Leave "Deploy to Development" ticked.)
3. The run stages the package, creates a release in **Feature branches**,
   deploys to **Development**, and waits for `deploy.sh`'s gates.

A green workflow means the stack actually serves: every service reported
healthy *and* Kong routed a live request to one of them.

```bash
curl -sS https://api-dev.fixmytext.velobits.dev/health
```

## Ship main to Production

1. Merge to `main`, run the same workflow from `main` → release `1.0.<run>` in
   the **Release** channel deploys to Development.
2. Verify Development.
3. Octopus portal → project → Releases → `1.0.<run>` → **Deploy to Production**
   (approve the manual intervention if configured). Only Release-channel
   versions offer this button — a feature-branch release physically cannot reach
   Production, because its channel's lifecycle has no Production phase.

```bash
curl -sS https://api.fixmytext.velobits.dev/health
```

## What each deploy does to the running stack

Octopus purges and re-extracts the install directory, so bind mounts point at
new inodes and `deploy.sh` recreates whatever depends on them:

| | Development | Production |
|---|---|---|
| Recreate | whole stack (package files are bind-mounted everywhere) | only services whose rebuilt image differs, plus Kong unconditionally |
| Downtime | ~60–90 s | ~1 s on the API (Kong restart); none for services if nothing changed |
| Migrations | gated step before any new container serves | same |
| Images | built on the VM; ~10 min cold, minutes warm | same |

Migrations run **before** traffic and a failure there aborts the deploy.

## Roll back

Octopus keeps every release and package: open the previous release →
*Deploy to …*. Images are rebuilt from that release's packaged sources, hitting
the Docker layer cache.

> ⚠️ **Rollback does not undo migrations.** `deploy.sh` only ever runs
> `upgrade head`; it never downgrades. Rolling application code back under a
> migrated schema is safe only for additive migrations. For a destructive one,
> plan the down-path *before* you deploy it — expand/contract: ship the additive
> migration plus code that tolerates both shapes first, drop the old columns in
> a later release.

To recover a *configuration* mistake rather than a code one, edit the Octopus
variable and redeploy the **same** release. No new package is needed, and the
task log will show the corrected `.env` being rendered.

## Rotate a secret

1. Edit the variable in Octopus (Project → Variables), scoped to its environment.
2. Redeploy the current release for that environment.

Nothing to touch on the server: `.env` is re-rendered every deploy, so there is
no file to edit and no git-history risk.

Two values are **cross-repo** and must be rotated in both places or auth breaks:

- `KEYCLOAK_SERVICE_ACCOUNT_SECRET` — shared with velobits-infra's Octopus
  variables. Rotate in Keycloak, then update both projects, then redeploy both.
- The realm name, if it ever changes.

Rotating `SESSION_COOKIE_SECRET` invalidates every existing session cookie —
users get signed out. That is the intended behaviour after a suspected leak, but
do not do it casually.

## Where the secrets live

| Secret | Lives in | Protection |
|---|---|---|
| DB / Redis passwords, app secrets, API keys, SMTP | Octopus **sensitive variables** | AES-encrypted at rest, masked as `****` in task logs, write-only via the UI |
| GitHub → Octopus credential | **nowhere** | OIDC federation — short-lived per-run token, nothing stored |
| `.env` on the VM | rendered per deploy by `deploy.sh` | mode 600, root-owned; the whole directory is purged and recreated each deploy |
| Anything in git | — | nothing: `.gitignore` blocks `.env*`, and the templates hold only variable *names* |

`.env.example` is the **local-laptop** contract and must never be copied to a
server. The deployed contract is `octopus/env.*.template`.

## Audit

Every deploy records who triggered it, which version, which commit (version →
run number → Actions run), the full task log, and a variable snapshot with
sensitive values masked.

---

## Troubleshooting

Problems with a pipeline that *used to work*. For failures while first building
the pipeline, see
[octopus-setup.md Appendix C](octopus-setup.md#appendix-c--setup-time-failure-modes).

### The deploy never starts

| Symptom | Cause / fix |
|---|---|
| Workflow fails at "Require green CI for this commit" | Push the commit and let **Backend Test & Build** pass. A missing run is treated as failure by design. |
| Login step: `Could not find matching identity` / `Access denied` | The OIDC identity or the service account's permissions changed. The error prints the exact subject GitHub presented. |
| Target unhealthy in Octopus | `sudo systemctl status "Tentacle: velobits"` on the VM; polling needs outbound 10943 (default-open on Oracle egress). |
| Deploy queues forever | Octopus serialises deployments per project/environment — check for an earlier task still running. |

### The deploy fails partway

| Symptom | Cause / fix |
|---|---|
| Task log lists `#{...}` tokens, then `ERROR: unbound Octopus variables` | A required variable is missing or scoped to the wrong environment. Add it, redeploy the same release. |
| `unknown flag: --ignore-buildable`, or an `!override` parse error | docker compose < 2.24 on the VM — upgrade via `get.docker.com`. |
| Migrations fail on `CREATE EXTENSION pgcrypto` | The database user lacks the privilege; use `avnadmin` or grant it. |
| Migrations fail with a TLS / `sslmode` error | `DATABASE_URL` is asyncpg — it needs `?ssl=require`, not libpq's `?sslmode=require`. |
| Migrations hang then time out | The managed database's allowed-IP list no longer includes the VM's public IP (it changes if the VM is recreated). |
| Image build OOM-killed | The build needs headroom for five images; check `free -h` and whether the other environment's stack is also running. |
| A service never reports healthy | `docker logs <container>`. `RuntimeError: Refusing to start: missing required production configuration: …` names the empty variable exactly. |
| Kong healthy but the routing probe fails | `gateway/kong/kong.yml` routes to a service that is down or misnamed — a broken config still passes `kong health`. `docker logs kong-prod`. |

### The deploy went green but the API misbehaves

| Symptom | Cause / fix |
|---|---|
| 502 through Traefik | This stack is down, or Kong lost its alias on `velobits-proxy-net`. Check `docker network inspect velobits-proxy-net` for `kong` (dev) / `kong-prod` (prod). |
| 401 on every authenticated request | Issuer mismatch. `KEYCLOAK_ISSUER` must be the **browser-facing** realm URL while `KEYCLOAK_JWKS_URL` is the internal one — different values on purpose. Also check the realm: `Velobits` dev, `Velobits-Prod` prod. |
| 500s from `account-svc` on user management | Keycloak Admin API calls failing — `KEYCLOAK_SERVICE_ACCOUNT_SECRET` drifted from the value in Keycloak, or (prod) the client was never created. |
| CORS errors in the browser | Kong owns CORS at the edge (`gateway/kong/kong.yml`); the origin must be in its list. `ALLOWED_ORIGINS` is only the per-service fallback for requests that bypass Kong. |
| Certificate warning on the API hostname | The DNS record got switched to Cloudflare-**proxied**; second-level names must be DNS only. |
| `too many connections` from the database | Lower `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`, or check what else shares the managed service. |
| Rate limits firing far too early | `TRUSTED_PROXY_HOSTS` no longer matches the compose subnet, so every request looks like it comes from one IP. It is pinned to `172.29.0.0/16` (dev) / `172.28.0.0/16` (prod). |

### Useful commands on the VM

```bash
# Development
cd /opt/velobits/fixmytext-backend/development
DC="docker compose --profile dev -f docker-compose.yml -f octopus/docker-compose.deploy.yml"

# Production
cd /opt/velobits/fixmytext-backend/production
DC="docker compose -f docker-compose-prod.yml"

$DC ps                       # what is running, and health status
$DC logs -f --tail 100       # follow everything
$DC logs -f account-svc      # one service
$DC config                   # the fully merged, interpolated config

docker network inspect velobits-proxy-net \
  --format '{{range .Containers}}{{.Name}} {{end}}'

# Re-run migrations by hand (idempotent)
$DC --profile migrate run --rm --no-deps migrate      # prod
$DC --profile migrate run --rm --no-deps migrate-dev  # dev
```

Prefer redeploying over hand-editing anything in the install directory: the next
deploy purges it, so a manual fix silently disappears.
