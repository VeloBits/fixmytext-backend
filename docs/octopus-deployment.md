# Octopus Deployment Runbook — fixmytext-backend

Manual, branch-based deployments of the FixMyText backend to the Oracle Cloud
Ubuntu VM, through Octopus Deploy **Development** and **Production**
environments. Everything here runs on free tiers.

This repo is the **second** project on an Octopus instance that
[velobits-infra](https://github.com/VeloBits/velobits-infra) already set up. The
shared plumbing — Octopus Cloud instance, environments, lifecycles, the OIDC
service account, the VM, the Tentacle, ports 80/443 — is configured **once**, in
[velobits-infra/docs/octopus-deployment.md](https://github.com/VeloBits/velobits-infra/blob/main/docs/octopus-deployment.md).
**Do that first, then this.** Below covers only what is specific to the backend.

```
GitHub Actions ("Deploy via Octopus", any branch, manual trigger)
  │  CI gate → stage compose + octopus + services/ + shared/ → fixmytext-backend.<version>.zip
  ▼
Octopus Cloud            release + channel + lifecycle (shared instance)
  │  polling Tentacle — VM dials OUT to Octopus :10943; no inbound ports
  ▼
Oracle Ubuntu VM (Tentacle target, roles: velobits-docker-host)
     extract package → render .env from sensitive variables → octopus/deploy.sh
     ├─ Development: docker-compose.yml + octopus/docker-compose.deploy.yml
     │    --profile dev, Kong exposed to Traefik as `kong`
     └─ Production:  docker-compose-prod.yml
          Kong exposed as `kong-prod`, no published host ports at all

     images:   BUILT ON THE VM from packaged sources (arm64 target)
     database: remote managed Postgres (Aiven free plan), separate database
               per environment — the VM runs no database container
     redis:    on the VM (ephemeral counters + the arq job queue)
```

Traefik routes `api-dev.fixmytext.velobits.dev` / `api.fixmytext.velobits.dev`
to this stack's Kong. Those routers live in the infra repo
(`traefik/rules/fixmytext-dev.yml`, `traefik/rules-prod/fixmytext-prod.yml`); the
hostname convention itself is documented in `velobits-infra/traefik/README.md`.

Repo files that make this work:

- [.github/workflows/deploy-octopus.yml](../.github/workflows/deploy-octopus.yml) — the manual pipeline
- [octopus/deploy.sh](../octopus/deploy.sh) — runs on the VM per deploy; picks the stack from `DEPLOY_ENV`
- [octopus/env.dev.template](../octopus/env.dev.template) / [octopus/env.prod.template](../octopus/env.prod.template) — Octopus-variable → `.env` mapping
- [octopus/docker-compose.deploy.yml](../octopus/docker-compose.deploy.yml) — deploy-time override for the dev stack
- [docker-compose-prod.yml](../docker-compose-prod.yml) — the production stack
- [scripts/check-env-templates.sh](../scripts/check-env-templates.sh) — CI guard over the templates

---

## Part 1 — Prerequisites from the infra repo

Confirm all of these before starting; each is done once for the whole platform:

| Prerequisite | Where |
|---|---|
| Octopus Cloud instance, `Development` + `Production` environments | infra runbook Part 1–2 |
| Lifecycles `Velobits standard` and `Development only` | infra runbook Part 2 |
| Service account `github-actions-velobits-oidc` + org GitHub variables | infra runbook Part 5 |
| Oracle VM with Docker ≥ 2.24, Tentacle in polling mode, role `velobits-docker-host` | infra runbook Part 6 |
| Cloudflare Origin CA cert on the VM, ports 80/443 open | infra runbook Part 6 |
| The infra stack **deployed and running** (Traefik + Keycloak) | infra runbook Part 7 |

The last one is a hard runtime dependency, not just ordering: every service in
this stack fetches JWKS from Keycloak over `velobits-proxy-net`, and Traefik is
what terminates TLS for the API hostname. `deploy.sh` creates
`velobits-proxy-net` if it is missing so a first deploy cannot hard-fail on
ordering, but the API returns 502 until Traefik is up and tokens cannot be
validated until Keycloak is.

Note the two infra stacks cannot run side by side (both own :80/:443), and each
backend stack is pinned to its matching identity container — dev expects
`keycloak-dev`, prod expects `velobist-auth`. So run infra-dev with backend-dev,
and infra-prod with backend-prod. The two *backend* stacks do not collide with
each other (distinct project names, container names and networks).

## Part 2 — OIDC identity for this repo (once)

The service account is shared; each repo gets its own identity on it.

Octopus → Configuration → Users → Service Accounts →
`github-actions-velobits-oidc` → **OIDC Identities → Add**:

- Issuer: `https://token.actions.githubusercontent.com`
- Subject: `repo:VeloBits@146367091/fixmytext-backend@1192930434:ref:*`

GitHub embeds immutable org and repo IDs in the subject, so a plain
`repo:VeloBits/fixmytext-backend:ref:*` will **not** match. The IDs above came
from `gh api repos/VeloBits/fixmytext-backend --jq '.id,.owner.id'`; a failed
login also prints the exact presented subject. The `ref:*` wildcard is what
allows any-branch deploys.

No new GitHub variables are needed — `OCTOPUS_URL`,
`OCTOPUS_SERVICE_ACCOUNT_ID` and `OCTOPUS_SPACE` are org-level and already set.

## Part 3 — Managed database (once per environment)

Both environments use a remote managed Postgres; the VM stores no product data.
On the existing Aiven service (the one holding Keycloak's databases) create two
more databases, e.g. `fixmytext_dev` and `fixmytext_prod`.

Three things to get right:

1. **Extension.** The baseline migrations run
   `CREATE EXTENSION IF NOT EXISTS pgcrypto`, so the migration user must be
   allowed to create it (`avnadmin` is). Despite the local stack using the
   `pgvector/pgvector:pg16` image, no migration requires `vector` today — if a
   future one does, enable that extension before deploying it.
2. **Driver dialect.** `DATABASE_URL` is SQLAlchemy + **asyncpg**, which spells
   TLS as `?ssl=require` — *not* libpq's `?sslmode=require`. Copying the Aiven
   URI verbatim will fail to connect:
   ```
   postgresql+asyncpg://<user>:<pass>@<host>:<port>/fixmytext_prod?ssl=require
   ```
3. **Connection budget.** The free plan's connection cap is small and Keycloak
   shares the service. Only `account-svc` and `payments-svc` hold pools, sized by
   `DB_POOL_SIZE` (4) + `DB_MAX_OVERFLOW` (2) → 12 connections total. Raise
   those only after checking what the plan allows.

Also restrict the service's **allowed IP addresses** to the VM's public IP.

## Part 4 — DNS for the API hostnames (once per environment)

| Hostname | Record | Cloudflare proxy |
|---|---|---|
| `api-dev.fixmytext.velobits.dev` | A → VM public IP | **DNS only** (grey cloud) |
| `api.fixmytext.velobits.dev` | A → VM public IP | **DNS only** (grey cloud) |

These are *second-level* subdomains, and that has two consequences worth
internalising:

- A `*.velobits.dev` record does not cover them. Each needs its own A record (or
  a `*.fixmytext.velobits.dev` wildcard).
- Cloudflare's free Universal SSL edge certificate does not cover them either.
  **Proxied** (orange cloud) they serve a mismatched certificate; set them to
  DNS only so Traefik's Let's Encrypt certificate faces the browser directly.
  Proxying them anyway requires Advanced Certificate Manager (paid).

DNS must resolve to the VM **before** the first production deploy: Traefik
requests the certificate as soon as the router loads, and ACME failures back off.

## Part 5 — Octopus project (once)

**Project** (Projects → Add): name `fixmytext-backend` — the workflow references
this exact name — default lifecycle `Velobits standard`.

**Channels** (project → Channels), matching the infra project so branch routing
behaves identically:

| Channel | Lifecycle | Version rule (package `fixmytext-backend`) |
|---|---|---|
| `Release` (make default) | `Velobits standard` | Pre-release tag: `^$` (no tag — only `1.0.N` from main) |
| `Feature branches` | `Development only` | Pre-release tag: `.+` (branch builds like `0.0.N-my-branch`) |

The pipeline versions main builds `1.0.<run>` and branch builds
`0.0.<run>-<branch-slug>`, so the pre-release tag alone routes each release —
a feature-branch release physically cannot reach Production.

**Deployment process** → Add step → Package → **Deploy a Package**:

| Setting | Value |
|---|---|
| Step name | `Deploy fixmytext backend` |
| On targets in roles | `velobits-docker-host` |
| Package feed / ID | Built-in feed / `fixmytext-backend` |

**Configure features** — enable all three:

1. **Custom Installation Directory** →
   `/opt/velobits/fixmytext-backend/#{Octopus.Environment.Name | ToLower}`
   and tick **Purge this directory before installation**. Safe: runtime state is
   in Docker volumes or the remote database, and `.env` is re-rendered every
   deploy.
2. **Substitute Variables in Templates** → target files (one per line):

   ```
   octopus/env.dev.template
   octopus/env.prod.template
   ```

3. **Custom Deployment Scripts** → *Post-deployment script*, Bash:

   ```bash
   DEPLOY_ENV=$(get_octopusvariable "Octopus.Environment.Name") bash octopus/deploy.sh
   ```

Recommended before going live: **Add step → Manual Intervention Required**,
scoped to `Production` only, placed *before* the package step.

## Part 6 — Project variables

Project → Variables. Names map 1:1 to the templates; scope every value to its
environment. Mark 🔒 rows **Sensitive** (encrypted at rest, masked in logs).

Values not in these tables are hardcoded in the templates because they are
derived, not configured — `KEYCLOAK_URL`, `KEYCLOAK_JWKS_URL`,
`KEYCLOAK_ISSUER`, `TRUSTED_PROXY_HOSTS`, `FRONTEND_URL`, `ALLOWED_ORIGINS`,
`REDIS_URL`, and the session-cookie flags. Change those by editing the template
in git, which is the point: they are part of the deployment's shape, not per-run
knobs.

**Scoped to `Development`** ([octopus/env.dev.template](../octopus/env.dev.template)):

| Variable | Value | 🔒 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `fixmytext-dev` — keep stable (prefixes volume/label names) | |
| `DATABASE_URL` | asyncpg URL for the **dev** database, `?ssl=require` | 🔒 |
| `POSTGRES_PASSWORD` | any non-empty value (only the parked `local-db` fallback reads it) | 🔒 |
| `REDIS_PASSWORD` | `openssl rand -base64 24` | 🔒 |
| `KEYCLOAK_REALM` | `Velobits` | |
| `KEYCLOAK_AUDIENCE` | `fixmytext-backend` | |
| `KEYCLOAK_SERVICE_ACCOUNT_ID` | `account-svc` (optional) | |
| `KEYCLOAK_SERVICE_ACCOUNT_SECRET` | **must match velobits-infra's value** | 🔒 |
| `SECRET_KEY` | `openssl rand -base64 48` | 🔒 |
| `SESSION_COOKIE_SECRET` | `openssl rand -base64 48` | 🔒 |
| `INTERNAL_SHARED_SECRET` | `openssl rand -base64 48` | 🔒 |
| `GROQ_API_KEY` | from console.groq.com | 🔒 |
| `RAZORPAY_KEY_ID` / `_KEY_SECRET` / `_WEBHOOK_SECRET` | `rzp_test_…` pair | 🔒 |
| `FREE_USES_PER_TOOL_PER_DAY`, `DAILY_LOGIN_BONUS` | optional | |
| `EMAIL_BACKEND`, `SMTP_*`, `EMAIL_FROM` | optional | 🔒 password |
| `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `OTEL_*` | optional | 🔒 headers |

**Scoped to `Production`** ([octopus/env.prod.template](../octopus/env.prod.template)) —
same names plus the pool sizes, with these differences:

| Variable | Value | 🔒 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `fixmytext-prod` | |
| `DATABASE_URL` | asyncpg URL for the **prod** database | 🔒 |
| `KEYCLOAK_REALM` | `Velobits-Prod` | |
| `KEYCLOAK_SERVICE_ACCOUNT_ID` / `_SECRET` | **required** — prod has no bootstrap sidecar, so create this client per velobits-infra's `keycloak-production-setup.md` before the first deploy | 🔒 |
| `SECRET_KEY`, `SESSION_COOKIE_SECRET`, `INTERNAL_SHARED_SECRET` | **different values from Development** | 🔒 |
| `RAZORPAY_KEY_ID` / `_KEY_SECRET` / `_WEBHOOK_SECRET` | **live** keys; register the webhook at `https://api.fixmytext.velobits.dev/api/v1/subscription/webhook` | 🔒 |
| `EMAIL_BACKEND`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM` | **required** — verification mail is part of signup | 🔒 password |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | optional, default 4 / 2 | |

Omitted optional variables render empty and the stack degrades gracefully. If a
**required** one is missing, `deploy.sh` fails fast with the unbound token name
printed in the task log.

`ENVIRONMENT=production` in the prod template is what arms every startup guard:
each service refuses to boot on an empty `KEYCLOAK_ISSUER`, `KEYCLOAK_AUDIENCE`,
`SESSION_COOKIE_SECRET` or `INTERNAL_SHARED_SECRET`, on
`TRUSTED_PROXY_HOSTS="*"`, on `SESSION_COOKIE_SECURE=false`, and on any "fake"
AI or payments backend. A misconfigured prod deploy fails loudly at container
start rather than serving traffic with a check silently disabled. Do not soften
this to get a deploy through.

## Part 7 — The deployment lifecycle, day to day

**Deploy any branch to Development**

1. Push your branch and let **Backend Test & Build** go green — the deploy
   workflow refuses to run otherwise (H-7), and treats a missing CI run as a
   failure rather than a skip.
2. GitHub → Actions → **Deploy via Octopus** → *Run workflow* → pick the branch
   → Run. (Leave "Deploy to Development" ticked.)
3. The run stages the package, creates a release in **Feature branches**,
   deploys to **Development**, and waits for `deploy.sh`'s gates. A green
   workflow means the stack actually serves: every service reported healthy and
   Kong routed a real request to one of them.

**Ship main to Production**

1. Merge to `main`, run the same workflow from `main` → release `1.0.<run>` in
   the **Release** channel deploys to Development.
2. Verify Development, then in the Octopus portal: project → Releases →
   `1.0.<run>` → **Deploy to Production** (approve the manual intervention if
   you added it). Only Release-channel versions offer this button.
3. The Production deploy builds the four service images plus the migration image
   on the VM, runs `alembic upgrade head` as a gated step, starts the stack, and
   gates on health + a Kong routing probe. First build ≈ 10 min; unchanged
   layers are cached after that.

**What each deploy does to the running stack** — Octopus purges and re-extracts
the install directory, so bind mounts point at new inodes and `deploy.sh`
recreates what depends on them:

- **Development**: whole stack recreated (package files are bind-mounted
  everywhere). ~60–90 s of downtime.
- **Production**: services are self-contained images, so compose restarts one
  only if its rebuilt image actually differs — an unchanged redeploy is
  zero-downtime. Kong is recreated unconditionally (it bind-mounts
  `gateway/kong/kong.yml`); that is a ~1 s blip on the API.

Migrations run **before** any new container serves traffic, and a failure there
aborts the deploy. They are not reversed automatically — see rollback.

**Roll back** — Octopus keeps every release and package: open the previous
release → *Deploy to …*. Images are rebuilt from that release's packaged
sources, hitting the layer cache.

⚠️ **Rollback does not undo migrations.** `deploy.sh` runs `upgrade head` only;
it never downgrades. Rolling application code back under a migrated schema is
safe only for additive migrations. For a destructive one, plan the down-path
before you deploy it (expand/contract: ship the additive migration and the code
that tolerates both shapes first, drop the old columns in a later release).

**Audit** — every deploy records who, what version, which commit (version → run
number → Actions run), the full task log, and a variable snapshot with sensitive
values masked.

## Securing secrets

Same model as the infra repo: Octopus **sensitive variables** hold everything
(AES-encrypted at rest, masked in task logs, write-only via the UI); the
GitHub↔Octopus connection is **OIDC**, so no API key is stored in GitHub; the
`.env` on the VM is rendered per deploy at mode 600 and lives in a directory
that is purged and recreated every time. `.gitignore` blocks `.env*`, and the
templates hold only variable *names*.

Rotation = edit the variable in Octopus → redeploy the current release. Nothing
to touch on the server, no git history risk.

Two cross-repo values must be rotated in **both** places or auth breaks:
`KEYCLOAK_SERVICE_ACCOUNT_SECRET` (shared with velobits-infra) and the realm
name if it ever changes.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Workflow fails at "Require green CI for this commit" | Push the commit and let **Backend Test & Build** pass. A never-run CI reports `missing` and is treated as failure by design. |
| Task log: `unbound Octopus variables` + token names | Add the listed variables (Part 6), scoped to the failing environment; redeploy the same release. |
| `create-release` can't find channel | Channel names must match the workflow exactly: `Release`, `Feature branches`. |
| Login step: `Could not find matching identity` | The OIDC subject must include the immutable IDs (Part 2); the error prints the exact presented subject — copy from there. |
| `unknown flag: --ignore-buildable` / `!override` parse error | docker compose < 2.24 on the VM — upgrade via `get.docker.com`. |
| Migrations fail on `CREATE EXTENSION pgcrypto` | The database user lacks the privilege; use `avnadmin` or grant it (Part 3). |
| Migrations fail with `sslmode` / TLS errors | `DATABASE_URL` is asyncpg — it needs `?ssl=require`, not `?sslmode=require` (Part 3). |
| A service never reports healthy | `docker logs <container>`. A `RuntimeError: Refusing to start: missing required production configuration: …` names the empty variable exactly. |
| Kong healthy but the routing probe fails | `gateway/kong/kong.yml` routes to a service that is down or misnamed. `docker logs kong-prod`. |
| API returns 502 through Traefik | This stack is down, or Kong is not on `velobits-proxy-net` under the expected alias (`kong` dev / `kong-prod` prod). Check `docker network inspect velobits-proxy-net`. |
| 401s on every authenticated request | Issuer mismatch: `KEYCLOAK_ISSUER` must be the **browser-facing** realm URL, while `KEYCLOAK_JWKS_URL` is the internal one. They are different values on purpose. |
| Browser shows a certificate warning on the API host | The DNS record is Cloudflare-**proxied**; second-level names need DNS only (Part 4). |
| `too many connections` from the database | Lower `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`, or check what else shares the managed service (Part 3). |
