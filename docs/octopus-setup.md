# Octopus Setup Guide — fixmytext-backend

**One-time setup**, click by click: everything you configure before the first
deploy can run. Day-to-day deploying, promoting, rolling back and troubleshooting
lives in [octopus-deployment.md](octopus-deployment.md).

Work through the stages in order. Each step says whether it is **shared** (done
once for the whole VeloBits platform — if you already set up
[velobits-infra](https://github.com/VeloBits/velobits-infra), verify and move
on) or **this repo** (new work, even if infra is already deployed).

---

## Contents

- [What you are building](#what-you-are-building)
- [Cost](#cost)
- [Stage A — Platform (shared)](#stage-a--platform-shared)
- [Stage B — External dependencies (this repo)](#stage-b--external-dependencies-this-repo)
- [Stage C — The Octopus project (this repo)](#stage-c--the-octopus-project-this-repo)
- [Stage D — Variables (this repo)](#stage-d--variables-this-repo)
- [Stage E — First deploy to Development](#stage-e--first-deploy-to-development)
- [Stage F — First promotion to Production](#stage-f--first-promotion-to-production)
- [Appendix A — Variable reference](#appendix-a--variable-reference)
- [Appendix B — What deploy.sh does](#appendix-b--what-deploysh-does)
- [Appendix C — Setup-time failure modes](#appendix-c--setup-time-failure-modes)

---

## What you are building

```
GitHub Actions — "Deploy via Octopus" (manual, any branch)
  │  ① CI gate: the commit's "Backend Test & Build" run must be green
  │  ② stage compose + octopus/ + services/ + shared/ → zip
  │  ③ push package, create release, (optionally) deploy to Development
  ▼
Octopus Cloud — one instance, shared with velobits-infra
  │  project "fixmytext-backend", channels route by version:
  │    main         → 1.0.<run>            → Release channel  → Dev, then Prod
  │    any branch   → 0.0.<run>-<slug>     → Feature branches → Dev only
  ▼  polling Tentacle: the VM dials OUT to :10943, no inbound ports
Oracle Ubuntu VM (Ampere A1, arm64) — role: velobits-docker-host
  │  ④ purge + extract package into /opt/velobits/fixmytext-backend/<env>
  │  ⑤ substitute variables into octopus/env.<env>.template
  │  ⑥ run octopus/deploy.sh
  ▼
  Development                          Production
  docker-compose.yml                   docker-compose-prod.yml
   + octopus/docker-compose.deploy.yml
  Kong reachable as kong:8000          Kong reachable as kong-prod:8000
  api-dev.fixmytext.velobits.dev       api.fixmytext.velobits.dev
        │                                     │
        └──── Traefik (velobits-infra) ───────┘  terminates TLS on :443
```

When you are done, this exists:

| Thing | Where | Shared? |
|---|---|---|
| Octopus Cloud instance | `https://<name>.octopus.app` | shared |
| Environments `Development`, `Production` | Octopus | shared |
| Lifecycles `Velobits standard`, `Development only` | Octopus | shared |
| Deployment target `oracle-vm-1`, role `velobits-docker-host` | Octopus + VM | shared |
| Service account `github-actions-velobits-oidc` | Octopus | shared |
| OIDC identity for `fixmytext-backend` | on that service account | **this repo** |
| Project `fixmytext-backend` + 2 channels + 1 process step | Octopus | **this repo** |
| ~20 project variables × 2 environments | Octopus | **this repo** |
| Databases `fixmytext_dev`, `fixmytext_prod` | managed Postgres | **this repo** |
| DNS `api-dev.fixmytext…`, `api.fixmytext…` | Cloudflare | **this repo** |

## Cost

| Piece | Cost |
|---|---|
| Octopus Cloud **Starter** | Free — up to 10 targets, 10 projects, 10 users |
| GitHub Actions | Free org minutes (~3 min/run; no image builds happen here) |
| Oracle VM | Always-free Ampere A1 shape |
| Managed Postgres | [Aiven free plan](https://aiven.io/free-postgresql-database) — 1 GB, backups included |
| Secret storage | Octopus sensitive variables + GitHub OIDC — $0 |

Two Octopus projects (infra + this) and one target stay well inside Starter.

---

## Stage A — Platform (shared)

If velobits-infra already deploys, **all of Stage A is done**. Verify with the
checklist at the end of the stage and skip to Stage B. The authoritative version
of these steps is
[velobits-infra/docs/octopus-deployment.md](https://github.com/VeloBits/velobits-infra/blob/main/docs/octopus-deployment.md)
Parts 1–6; they are summarised here so this guide reads end-to-end.

### A1. Octopus Cloud instance

1. Sign up at [octopus.com/start](https://octopus.com/start) → **Cloud** →
   instance name e.g. `velobits` → you get `https://velobits.octopus.app`.
   Starter is selected automatically while you stay ≤ 10 targets/projects/users.
2. Stay in the default space (`Default`), or create a `VeloBits` space — if you
   do, set the `OCTOPUS_SPACE` GitHub variable to match in A6.

### A2. Environments

Infrastructure → Environments → Add, twice:

1. `Development`
2. `Production`

Names are case-sensitive: `deploy.sh` lowercases `Octopus.Environment.Name` and
matches `development` / `production`. Anything else aborts the deploy with
`DEPLOY_ENV must be 'Development' or 'Production'`.

### A3. Lifecycles

Deploy → Lifecycles:

| Lifecycle | Phases | Used by |
|---|---|---|
| `Velobits standard` | Phase 1 `Development` → Phase 2 `Production` | the `Release` channel |
| `Development only` | Phase 1 `Development` | the `Feature branches` channel |

Leave "automatic deployment" **off** in both phases — releases deploy only when
you say so. The phase order is what enforces promotion: Octopus refuses to
deploy to Production until the release succeeded in Development.

### A4. Prepare the Oracle VM

SSH in, then:

**Docker Engine + Compose ≥ 2.24** — the dev deploy override uses the compose
`!override` tag, which older versions cannot parse:

```bash
curl -fsSL https://get.docker.com | sudo sh
docker compose version   # want >= 2.24
```

**Shared network** — velobits-infra creates `velobits-proxy-net`, and
`deploy.sh` creates it if missing, so this is belt-and-braces:

```bash
sudo docker network create velobits-proxy-net
```

**Cloudflare Origin CA certificate** — proxied hostnames terminate TLS at
Cloudflare's edge, which then makes its own TLS connection to this host; without
a real certificate here Cloudflare returns **error 525**. Create one in the
Cloudflare dashboard (SSL/TLS → Origin Server → Create Certificate) for
`velobits.dev, *.velobits.dev, *.fixmytext.velobits.dev`, validity 15 years, and
save both PEM blocks where `traefik/rules/tls.yml` expects them:

```bash
sudo mkdir -p /opt/velobits/certs
sudo nano /opt/velobits/certs/velobits-dev.crt   # paste the certificate
sudo nano /opt/velobits/certs/velobits-dev.key   # paste the private key
sudo chmod 600 /opt/velobits/certs/velobits-dev.key
```

That directory sits **outside** any purged install directory, so it survives
deploys. Then set Cloudflare → SSL/TLS → Overview → mode **Full (strict)**.

**Firewall** — allow inbound TCP **80 and 443** in the Oracle VCN security list
or NSG. 443 serves traffic; 80 is needed for Let's Encrypt's HTTP-01 challenge.
No inbound port is needed for deploys themselves (A5). Docker publishes ports
through its own iptables chains, so the host firewall usually needs nothing
extra — if a port is still unreachable, check `/etc/iptables/rules.v4`, since
Oracle images ship a restrictive default.

### A5. Install the Tentacle in polling mode

```bash
sudo apt-key adv --fetch-keys https://apt.octopus.com/public.key
sudo add-apt-repository "deb https://apt.octopus.com/ stable main"
sudo apt-get update && sudo apt-get install -y tentacle
sudo /opt/octopus/tentacle/configure-tentacle.sh
```

Interactive answers:

| Prompt | Answer |
|---|---|
| Instance name | `velobits` (default fine) |
| Kind | **Polling** |
| Octopus URL | `https://velobits.octopus.app` |
| API key | a temporary key from *your* user (Profile → API Keys); revoke it after registration |
| Space | `Default` (or yours) |
| Register as | Deployment target |
| Environments | `Development,Production` |
| Roles | `velobits-docker-host` |
| Name | `oracle-vm-1` |

**Polling** matters: the Tentacle dials out to Octopus Cloud on 10943, so you
open no inbound ports for deployment. Verify: Infrastructure → Deployment
targets → `oracle-vm-1` shows **Healthy** in both environments.

> The Tentacle service runs as root by default, which is how it gets Docker
> access. Confining it to a dedicated user in the `docker` group is worthwhile
> later hardening (docker-group membership is still root-equivalent, but it keeps
> Octopus's file paths contained).

### A6. GitHub ↔ Octopus over OIDC

No API key is stored in GitHub — the workflow exchanges a GitHub-signed OIDC
token for a short-lived Octopus token per run.

1. Octopus → Configuration → Users → **Service Accounts** → Add:
   `github-actions-velobits-oidc`. Grant it a team/role that can **create
   releases, push packages, and deploy** in your space (Project Deployer +
   Package Publisher, or Space Manager while you are solo).
2. Copy the service account **ID** from its page.
3. GitHub → **Organization** Settings → Secrets and variables → Actions →
   **Variables**:

   | Variable | Value |
   |---|---|
   | `OCTOPUS_URL` | `https://velobits.octopus.app` |
   | `OCTOPUS_SERVICE_ACCOUNT_ID` | the ID from step 2 |
   | `OCTOPUS_SPACE` | only if not `Default` |

Org-level means every VeloBits repo inherits them; repo-level works too. One
service account serves all repos — accounts are instance-level and permissions
come from team membership — and it can hold **one OIDC identity per repo**. This
repo's identity is added in [C1](#c1-oidc-identity-for-this-repo).

### Stage A verification

- [ ] `https://<instance>.octopus.app` loads
- [ ] Environments `Development` and `Production` exist, spelled exactly so
- [ ] Both lifecycles exist, with automatic deployment off
- [ ] `docker compose version` on the VM ≥ 2.24
- [ ] `sudo docker network ls | grep velobits-proxy-net` returns a row
- [ ] `/opt/velobits/certs/velobits-dev.{crt,key}` exist, key is mode 600
- [ ] Target `oracle-vm-1` is Healthy in both environments
- [ ] Org variables `OCTOPUS_URL` and `OCTOPUS_SERVICE_ACCOUNT_ID` are set
- [ ] **velobits-infra is deployed and running** — see the note below

The last item is a hard runtime dependency, not just ordering. Every service in
this stack fetches JWKS from Keycloak over `velobits-proxy-net`, and Traefik is
what terminates TLS for the API hostname. Deploy this stack without infra and
you get 502s from the edge and services that cannot validate a token.

Note also that infra-dev and infra-prod **cannot run side by side** (both own
:80/:443), and each backend stack is pinned to its matching identity container —
dev expects `keycloak-dev`, prod expects `velobits-auth`. So pair dev with dev
and prod with prod. The two *backend* stacks do not collide with each other:
distinct project names, container names and networks.

---

## Stage B — External dependencies (this repo)

### B1. Managed Postgres databases

Both environments use a remote managed Postgres; the VM stores no product data
(`db-service` and `pgbouncer` are parked behind a `local-db` profile on
deploys). On the existing Aiven service — the one already holding Keycloak's
databases — create two more:

- `fixmytext_dev`
- `fixmytext_prod`

Then get three things right, each of which has bitten this setup:

**1. The `pgcrypto` extension.** Both baseline migrations run
`CREATE EXTENSION IF NOT EXISTS pgcrypto`, so the migration user must be allowed
to create it (`avnadmin` is). Verify before deploying:

```bash
psql "<uri>" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" -c "\dx"
```

Despite the local stack using the `pgvector/pgvector:pg16` image, no migration
requires the `vector` extension today. If one ever does, enable it first.

**2. The driver dialect.** `DATABASE_URL` is SQLAlchemy + **asyncpg**, which
spells TLS `?ssl=require` — *not* libpq's `?sslmode=require`. Pasting the Aiven
URI verbatim fails to connect:

```
postgresql+asyncpg://<user>:<pass>@<host>:<port>/fixmytext_prod?ssl=require
```

**3. The connection budget.** The free plan's connection cap is small and
Keycloak shares the service. Only `account-svc` and `payments-svc` hold pools,
sized by `DB_POOL_SIZE` (4) + `DB_MAX_OVERFLOW` (2) → 12 connections total.
Check the plan's limit before raising either.

Finally, restrict the service's **allowed IP addresses** to the VM's public IP
instead of the default open-to-all, and pick the Aiven region closest to the VM.

### B2. DNS and Cloudflare

| Hostname | Record | Cloudflare proxy |
|---|---|---|
| `api-dev.fixmytext.velobits.dev` | A → VM public IP | **DNS only** (grey cloud) |
| `api.fixmytext.velobits.dev` | A → VM public IP | **DNS only** (grey cloud) |

These are *second-level* subdomains, with two consequences:

- A `*.velobits.dev` record does not cover them. Each needs its own A record (or
  a `*.fixmytext.velobits.dev` wildcard).
- Cloudflare's free Universal SSL edge certificate does not cover them either.
  **Proxied** (orange cloud), they serve a mismatched certificate. Set them to
  DNS only so Traefik's Let's Encrypt certificate faces the browser directly,
  which is what `traefik/rules-prod/fixmytext-prod.yml` expects. Proxying anyway
  requires Advanced Certificate Manager (paid).

The identity host `auth.velobits.dev` is first-level and stays proxied — it uses
the Origin CA certificate from [A4](#a4-prepare-the-oracle-vm).

DNS must resolve to the VM **before** the first production deploy: Traefik
requests the certificate as soon as the router loads, and ACME failures back off.

```bash
dig +short api.fixmytext.velobits.dev      # expect the VM's IP, not a Cloudflare IP
```

### B3. The Keycloak service account

`account-svc` calls the Keycloak Admin API using a dedicated service-account
client rather than master-realm admin credentials.

- **Development**: velobits-infra's `bootstrap.sh` creates the client on every
  deploy. You only need to copy its secret into this project's variables, and
  the values **must match** velobits-infra's Octopus variables.
- **Production**: the prod identity stack has **no bootstrap sidecar** — create
  the client by hand per
  [velobits-infra/docs/keycloak-production-setup.md](https://github.com/VeloBits/velobits-infra/blob/main/docs/keycloak-production-setup.md)
  **before** the first production deploy, or `account-svc` starts but every
  Admin API call fails.

Realm names: `Velobits` in dev, `Velobits-Prod` in prod. (`Velobits-Dev` never
existed, despite having been a default in a few places.)

---

## Stage C — The Octopus project (this repo)

### C1. OIDC identity for this repo

Octopus → Configuration → Users → Service Accounts →
`github-actions-velobits-oidc` → **OIDC Identities → Add**:

- **Issuer**: `https://token.actions.githubusercontent.com`
- **Subject**: `repo:VeloBits@146367091/fixmytext-backend@1192930434:ref:*`

GitHub embeds **immutable org and repo IDs** in the subject, so a plain
`repo:VeloBits/fixmytext-backend:ref:*` will *not* match. Those IDs came from:

```bash
gh api repos/VeloBits/fixmytext-backend --jq '.id, .owner.id'
# 1192930434   ← repo id
# 146367091    ← owner id
```

A failed login also prints the exact subject GitHub presented — copy from there
if in doubt. The `ref:*` wildcard is what permits any-branch deploys.

Give each repo its own identity. Avoid a `repo:VeloBits*` catch-all, so a rogue
workflow in one repo cannot be broadened accidentally.

### C2. Create the project

Projects → Add:

| Setting | Value |
|---|---|
| Name | `fixmytext-backend` — the workflow references this exact string |
| Default lifecycle | `Velobits standard` |

The name is `env.OCTOPUS_PROJECT` in
[deploy-octopus.yml](../.github/workflows/deploy-octopus.yml); a mismatch fails
at "Create release".

### C3. Channels

Project → Channels. Create both, and make `Release` the default:

| Channel | Lifecycle | Version rule (package `fixmytext-backend`) |
|---|---|---|
| `Release` | `Velobits standard` | Pre-release tag: `^$` |
| `Feature branches` | `Development only` | Pre-release tag: `.+` |

This is what makes "any branch → dev only, main → promotable" work without any
branch logic in Octopus. The workflow versions main builds `1.0.<run>` (no
prerelease tag) and branch builds `0.0.<run>-<branch-slug>` (a prerelease tag),
so the tag alone routes each release. A feature-branch release is *physically*
unable to reach Production, because its channel's lifecycle has no Production
phase.

Channel names must match the workflow exactly: `Release`, `Feature branches`.

### C4. The deployment process

Project → Process → **Add step → Package → Deploy a Package**:

| Setting | Value |
|---|---|
| Step name | `Deploy fixmytext backend` |
| On targets in roles | `velobits-docker-host` |
| Package feed | Built-in feed |
| Package ID | `fixmytext-backend` |

Then click **Configure features** and enable **all three**:

**1. Custom Installation Directory**

```
/opt/velobits/fixmytext-backend/#{Octopus.Environment.Name | ToLower}
```

Tick **Purge this directory before installation**. Safe: runtime state lives in
Docker volumes or the remote database, and `.env` is re-rendered every deploy.
The per-environment path is what lets dev and prod coexist on one host.

**2. Substitute Variables in Templates** — target files, one per line:

```
octopus/env.dev.template
octopus/env.prod.template
```

Both are listed even though each deploy uses one. Octopus substitutes both; only
the selected template is copied to `.env`, and `deploy.sh` checks *only* that one
for unbound tokens — so leftover tokens in the other environment's template are
expected and harmless.

**3. Custom Deployment Scripts** → *Post-deployment script*, **Bash**:

```bash
DEPLOY_ENV=$(get_octopusvariable "Octopus.Environment.Name") bash octopus/deploy.sh
```

That single line is the whole deployment. `deploy.sh` picks the stack, the
template and the container names from `DEPLOY_ENV` — see
[Appendix B](#appendix-b--what-deploysh-does).

### C5. Production approval (recommended)

Add step → **Manual Intervention Required**, scoped to the `Production`
environment only, positioned **before** the package step. That gives you an
explicit approval click on every production deploy. Skip it and promotion is a
single button with no second confirmation.

---

## Stage D — Variables (this repo)

Project → Variables. Every name maps 1:1 to a token in
`octopus/env.*.template`. **Scope every value to its environment** — the two
environments have separate values for almost everything.

Mark 🔒 rows as type **Sensitive**: encrypted at rest, masked as `****` in task
logs, write-only through the UI.

### D1. Generate the secrets

```bash
# Run once per environment — dev and prod must NOT share these.
for k in SECRET_KEY SESSION_COOKIE_SECRET INTERNAL_SHARED_SECRET; do
  printf '%-24s %s\n' "$k" "$(openssl rand -base64 48)"
done
printf '%-24s %s\n' REDIS_PASSWORD "$(openssl rand -base64 24)"
```

### D2. Scoped to `Development`

Template: [octopus/env.dev.template](../octopus/env.dev.template)

| Variable | Value | 🔒 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `fixmytext-dev` — keep stable, it prefixes volume/label names | |
| `DATABASE_URL` | asyncpg URL for `fixmytext_dev`, `?ssl=require` | 🔒 |
| `POSTGRES_PASSWORD` | any non-empty value — only the parked `local-db` fallback reads it, but compose interpolates the whole file before profiles apply, so it must resolve | 🔒 |
| `REDIS_PASSWORD` | `openssl rand -base64 24` | 🔒 |
| `KEYCLOAK_REALM` | `Velobits` | |
| `KEYCLOAK_AUDIENCE` | `fixmytext-backend` | |
| `KEYCLOAK_SERVICE_ACCOUNT_ID` | `account-svc` (optional) | |
| `KEYCLOAK_SERVICE_ACCOUNT_SECRET` | **must match velobits-infra's value** | 🔒 |
| `SECRET_KEY` | `openssl rand -base64 48` | 🔒 |
| `SESSION_COOKIE_SECRET` | `openssl rand -base64 48` | 🔒 |
| `INTERNAL_SHARED_SECRET` | `openssl rand -base64 48` | 🔒 |
| `GROQ_API_KEY` | from console.groq.com | 🔒 |
| `RAZORPAY_KEY_ID` | `rzp_test_…` | 🔒 |
| `RAZORPAY_KEY_SECRET` | test secret | 🔒 |
| `RAZORPAY_WEBHOOK_SECRET` | test webhook secret | 🔒 |
| `FREE_USES_PER_TOOL_PER_DAY` | optional (default 3) | |
| `DAILY_LOGIN_BONUS` | optional (default 1) | |
| `EMAIL_BACKEND`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USERNAME`, `EMAIL_FROM` | optional | |
| `SMTP_PASSWORD` | optional | 🔒 |
| `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_RELEASE`, `OTEL_EXPORTER_OTLP_ENDPOINT` | optional | |
| `OTEL_EXPORTER_OTLP_HEADERS` | optional | 🔒 |

### D3. Scoped to `Production`

Template: [octopus/env.prod.template](../octopus/env.prod.template)

Same names, with these differences — the rest carry the same meaning:

| Variable | Value | 🔒 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `fixmytext-prod` | |
| `DATABASE_URL` | asyncpg URL for `fixmytext_prod` | 🔒 |
| `KEYCLOAK_REALM` | `Velobits-Prod` | |
| `KEYCLOAK_SERVICE_ACCOUNT_ID` / `_SECRET` | **required** — created by hand per [B3](#b3-the-keycloak-service-account) | 🔒 |
| `SECRET_KEY`, `SESSION_COOKIE_SECRET`, `INTERNAL_SHARED_SECRET` | **different values from Development** | 🔒 |
| `RAZORPAY_KEY_ID` / `_KEY_SECRET` / `_WEBHOOK_SECRET` | **live** keys; register the webhook at `https://api.fixmytext.velobits.dev/api/v1/subscription/webhook` | 🔒 |
| `EMAIL_BACKEND`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM` | **required** — verification mail is part of signup | 🔒 password |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | optional, default 4 / 2 | |

An omitted **optional** variable renders empty and the stack degrades
gracefully. An omitted **required** one leaves its `#{TOKEN}` in place, and
`deploy.sh` aborts with the token name printed in the task log — it never
deploys a half-configured environment.

### D4. What is deliberately *not* a variable

These live in the templates in git, not in Octopus, because they are part of the
deployment's shape rather than per-run configuration. Change them with a commit
and a review, not a form field:

| Setting | Value | Why it is fixed |
|---|---|---|
| `ENVIRONMENT` | `development` / `production` | Arms the startup guards. Making it editable would let someone disable every security check from a text box. |
| `KEYCLOAK_URL`, `KEYCLOAK_JWKS_URL` | internal container names | Server-to-server. The public hostname resolves through Cloudflare from inside a container, not to the local Traefik. |
| `KEYCLOAK_ISSUER` | public realm URL | The browser-facing value, because that is what Keycloak stamps into the token's `iss`. Different from the JWKS host **on purpose**. |
| `TRUSTED_PROXY_HOSTS` | `172.29.0.0/16` dev, `172.28.0.0/16` prod | Must match the pinned compose subnet. A wildcard here lets any caller spoof `X-Forwarded-For` past the rate limiter. |
| `SESSION_COOKIE_SECURE` | `true` | Deployed environments are HTTPS-only. |
| `SESSION_COOKIE_DOMAIN` | empty (host-only) | The API and the frontend are different hosts; a shared parent Domain would widen the cookie for nothing. |
| `FRONTEND_URL`, `ALLOWED_ORIGINS` | the environment's frontend hostnames | Follows the platform hostname convention. |
| `REDIS_URL` | built from `#{REDIS_PASSWORD}` | Derived — two sources of truth would drift. |

`ENVIRONMENT=production` is what arms every startup guard: each service refuses
to boot on an empty `KEYCLOAK_ISSUER`, `KEYCLOAK_AUDIENCE`,
`SESSION_COOKIE_SECRET` or `INTERNAL_SHARED_SECRET`, on
`TRUSTED_PROXY_HOSTS="*"`, on `SESSION_COOKIE_SECURE=false`, and on any "fake"
AI or payments backend. A misconfigured production deploy fails loudly at
container start instead of serving traffic with a check silently off. **Do not
soften this to get a deploy through.**

`scripts/check-env-templates.sh` enforces the invariants above in CI, so a
template edit that drops a required key or reintroduces a wildcard fails the
build:

```bash
bash scripts/check-env-templates.sh
```

---

## Stage E — First deploy to Development

### E1. Pre-flight checklist

- [ ] Stage A verification list all ticked
- [ ] velobits-infra **dev** stack running (`docker ps` shows `keycloak-dev`, `velobits-traefik`)
- [ ] `fixmytext_dev` database reachable, `pgcrypto` creatable
- [ ] `api-dev.fixmytext.velobits.dev` resolves to the VM, grey cloud
- [ ] OIDC identity added for this repo ([C1](#c1-oidc-identity-for-this-repo))
- [ ] Project, both channels, and the process step configured (C2–C4)
- [ ] All Development variables set and scoped ([D2](#d2-scoped-to-development))
- [ ] Your branch is pushed and **"Backend Test & Build" is green on it**

The last one is a hard gate: the workflow reads the latest
"Backend Test & Build" conclusion for the exact commit and refuses to deploy
anything that is not `success`. A never-run CI reports `missing` and is treated
as a failure, not a skip.

### E2. Run it

GitHub → Actions → **Deploy via Octopus** → *Run workflow* → pick the branch →
leave "Deploy the release to Development" ticked → **Run workflow**.

The workflow: gates on CI → computes version and channel → stages the package →
logs in to Octopus over OIDC → pushes the package → creates the release →
deploys to Development → waits for the Octopus task to finish. A green workflow
therefore means the stack is actually serving, not merely that files copied.

### E3. What the Octopus task log should look like

```
[deploy] environment: Development — template: octopus/env.dev.template
[deploy] .env rendered (43 entries, mode 600)
[deploy] Docker Compose version v2.3x.x
[deploy] building service images on this host (--pull refreshes base images;
[deploy] first build takes several minutes, cached afterwards)
[deploy] pulling pinned images (kong, redis, postgres)
[deploy] running alembic migrations
[deploy] migrations at head
[deploy] starting stack
[deploy] waiting for fixmytext-account-svc to report healthy (max 300s)
[deploy] fixmytext-account-svc healthy
...                                    (ai, text, payments, kong in turn)
[deploy] smoke-testing Kong routing (fixmytext-account-svc -> kong:8000/health)
[deploy] Kong routing OK
[deploy] done — stack is up:
```

First run takes roughly 10 minutes (five images built from scratch); later
deploys are minutes, mostly cache hits.

If you instead see a list of `#{...}` tokens followed by
`ERROR: unbound Octopus variables above`, a required variable is missing or is
scoped to the wrong environment. Add it and redeploy the *same* release — no new
package needed.

### E4. Verify

```bash
# From outside — through Traefik on the real hostname
curl -sS https://api-dev.fixmytext.velobits.dev/health
# → {"status":"ok","version":"0.1.0"}

# On the VM
cd /opt/velobits/fixmytext-backend/development
docker compose --profile dev -f docker-compose.yml \
  -f octopus/docker-compose.deploy.yml ps

# Kong's alias must be present on the shared network, or Traefik 502s
docker network inspect velobits-proxy-net \
  --format '{{range .Containers}}{{.Name}} {{end}}'
```

Then exercise a real token: log in through
`https://fixmytext-dev.velobits.dev`, and confirm an authenticated call
succeeds. That is the end-to-end proof that JWKS resolves over the shared
network and the issuer matches — the two things most likely to be subtly wrong
on a first deploy.

---

## Stage F — First promotion to Production

Extra prerequisites beyond Stage E:

- [ ] velobits-infra **prod** stack deployed (`velobits-auth`, prod Traefik) —
      and remember it cannot run alongside the infra dev stack
- [ ] Keycloak prod service-account client created by hand ([B3](#b3-the-keycloak-service-account))
- [ ] `fixmytext_prod` database created, `pgcrypto` creatable, VM IP allow-listed
- [ ] `api.fixmytext.velobits.dev` resolves to the VM, **grey cloud**
- [ ] All Production variables set, with **different** secrets from dev
- [ ] Razorpay **live** keys in place and the webhook registered against the prod URL

Then:

1. Merge to `main` and run **Deploy via Octopus** from `main`. That produces
   `1.0.<run>` in the `Release` channel and deploys it to Development.
2. Verify Development.
3. Octopus → project → Releases → `1.0.<run>` → **Deploy to Production**
   (approving the manual intervention if you added it in
   [C5](#c5-production-approval-recommended)). Only Release-channel versions
   offer that button.

The production deploy builds the images on the VM, runs migrations as a gated
step, starts the stack with no published host ports, and gates on health plus
the Kong routing probe.

Then verify:

```bash
curl -sS https://api.fixmytext.velobits.dev/health
```

Day-two operations — redeploys, rollback, secret rotation, incident
troubleshooting — are in [octopus-deployment.md](octopus-deployment.md).

---

## Appendix A — Variable reference

How a value travels from Octopus to a running container:

```
Octopus project variable  (scoped to an environment, maybe Sensitive)
        │  "Substitute Variables in Templates" replaces #{TOKEN}
        ▼
octopus/env.<env>.template
        │  deploy.sh: cp "$TEMPLATE" .env   (umask 077 → mode 600)
        ▼
<package root>/.env
        │  compose reads it two ways:
        │    env_file:      → the container's environment
        │    ${VAR} interp  → values inside the compose file itself
        ▼
container environment  →  pydantic-settings  →  settings.<FIELD>
```

Consequences worth knowing:

- A variable can be **required by compose interpolation** even when its service
  is disabled by a profile — compose interpolates the whole file before applying
  profiles. That is why `POSTGRES_PASSWORD` must be set despite `db-service`
  being parked.
- `environment:` in a compose file **overrides** `env_file:`. The prod compose
  pins a few values (`ENVIRONMENT`, `SESSION_COOKIE_SECURE`,
  `SESSION_COOKIE_DOMAIN`) precisely so a stray `.env` value cannot weaken them.
- **Never put an inline comment after an empty value** in a template. For an
  empty value, compose's env_file parser keeps the comment *as the value* —
  this exact bug once put `# empty = host-only (intentional)` into the session
  cookie's `Domain` attribute. `check-env-templates.sh` now fails the build on
  the pattern.

## Appendix B — What deploy.sh does

[octopus/deploy.sh](../octopus/deploy.sh), in order:

| # | Step | Notes |
|---|---|---|
| 1 | Resolve the package root and pick the stack from `DEPLOY_ENV` | Sets the compose files, the migrate command, the container names to health-check, and whether to force-recreate everything. An unexpected value aborts. |
| 2 | Abort if the selected template still contains `#{` | Octostache leaves unmatched tokens in place, so a surviving token means a missing Octopus variable. Safe to print — the line holds the token, not a value. |
| 3 | `cp "$TEMPLATE" .env` under `umask 077` | Mode 600, root-owned, in a directory purged next deploy. |
| 4 | Create `velobits-proxy-net` if missing | This stack declares it `external`, and `up` aborts on a missing external network. Belt-and-braces for deploy ordering. |
| 5 | `compose config -q` | Validates the merged files, and catches compose < 2.24 (which cannot parse `!override`). |
| 6 | `compose build --pull`, then `pull --ignore-buildable` | Images built natively for arm64; pinned third-party images pulled. |
| 7 | Run alembic as an explicit gated step | `account-svc` first (it owns `auth.users`), then `payments-svc` (cross-schema FKs into it). `--no-deps` because the database is remote. A failure here aborts **before** any new container serves traffic. |
| 8 | `up -d` | Dev force-recreates everything (package files are bind-mounted, and Octopus purges the directory so every mount points at a new inode). Prod recreates only what changed, plus Kong unconditionally since it mounts `kong.yml`. |
| 9 | Wait for each service to report Docker-healthy (300 s each) | On timeout, dumps the last 100 log lines and fails. |
| 10 | Smoke-test Kong **routing** | A broken `kong.yml` still passes `kong health` while 404ing every request. Driven from a service container (python is guaranteed there; the Kong image has no dependable curl) against the `kong` network alias, so no published port is needed. |
| 11 | `docker image prune -f`, then `compose ps` | Dangling layers only; running images and pinned tags untouched. |

Every deploy therefore either ends green with a stack that provably serves, or
fails with the reason in the task log.

## Appendix C — Setup-time failure modes

Failures you hit while *building* the pipeline. Operational failures are in
[octopus-deployment.md](octopus-deployment.md#troubleshooting).

| Symptom | Cause / fix |
|---|---|
| Workflow fails at "Require green CI for this commit" | Push the commit and let **Backend Test & Build** pass. A never-run CI reports `missing`, treated as failure by design. |
| Login step: `Could not find matching identity` | The OIDC subject must carry the immutable GitHub IDs ([C1](#c1-oidc-identity-for-this-repo)). The error prints the exact presented subject — copy it. |
| Login step: `Access denied` | The service account lacks release/package/deploy permission in the space ([A6](#a6-github--octopus-over-oidc)). |
| "Create release" cannot find the channel | Channel names must match the workflow exactly: `Release`, `Feature branches`. |
| "Create release" cannot find the project | The project name must be exactly `fixmytext-backend`. |
| Deploy fails: no target found for role | The Tentacle's role must be `velobits-docker-host` and it must be registered in the environment being deployed to. |
| Task log lists `#{...}` tokens then aborts | Missing or wrongly-scoped Octopus variables ([Stage D](#stage-d--variables-this-repo)). Fix and redeploy the same release. |
| `unknown flag: --ignore-buildable`, or an `!override` parse error | docker compose < 2.24 on the VM — upgrade via `get.docker.com`. |
| Migrations fail on `CREATE EXTENSION pgcrypto` | The database user lacks the privilege — use `avnadmin` or grant it ([B1](#b1-managed-postgres-databases)). |
| Migrations fail with a TLS/`sslmode` error | `DATABASE_URL` is asyncpg: `?ssl=require`, not `?sslmode=require`. |
| Migrations hang, then time out | The managed database's allowed-IP list does not include the VM's public IP. |
| A service never reports healthy | `docker logs <container>`. `RuntimeError: Refusing to start: missing required production configuration: …` names the empty variable exactly. |
| Kong healthy but the routing probe fails | `gateway/kong/kong.yml` points at a service that is down or misnamed. |
| 502 through Traefik | This stack is down, or Kong is missing its alias on `velobits-proxy-net` (`kong` in dev, `kong-prod` in prod). |
| 401 on every authenticated request | Issuer mismatch. `KEYCLOAK_ISSUER` must be the browser-facing realm URL while `KEYCLOAK_JWKS_URL` is the internal one — different values on purpose. |
| Certificate warning on the API hostname | The DNS record is Cloudflare-proxied; second-level names must be DNS only ([B2](#b2-dns-and-cloudflare)). |
| Cloudflare error 525 on `auth.velobits.dev` | The Origin CA certificate is missing from the VM ([A4](#a4-prepare-the-oracle-vm)). |
| Deploying dev breaks prod (or vice versa) | The two **infra** stacks cannot coexist — both own :80/:443. Backend stacks do not conflict with each other. |
