#!/usr/bin/env bash
# Octopus post-deployment script for the fixmytext-backend package step.
#
# Runs on the VM's Tentacle from the package's custom installation directory
# (/opt/velobits/fixmytext-backend/development or .../production). Octopus
# invokes it from the step's post-deployment script as:
#
#   DEPLOY_ENV=$(get_octopusvariable "Octopus.Environment.Name") bash octopus/deploy.sh
#
# By then Octopus has already extracted the package (purging the directory
# first) and substituted project variables into octopus/env.*.template.
#
# What runs depends on the environment:
#   Development  docker-compose.yml + octopus/docker-compose.deploy.yml,
#                --profile dev. Product database is remote; the in-compose
#                Postgres and PgBouncer are parked behind `local-db`.
#   Production   docker-compose-prod.yml. Same remote-database shape, no host
#                port publishing, Kong exposed to Traefik as kong-prod.
#
# Both build their service images ON THIS HOST: the target is an Ampere A1
# (arm64) and this repo publishes no images anywhere, so building natively is
# both architecturally correct and free. Docker's layer cache makes unchanged
# rebuilds near-instant.
#
# One-time setup (Octopus project, variables, VM): docs/octopus-setup.md
# Day-to-day operations and troubleshooting:      docs/octopus-deployment.md
set -euo pipefail

# Resolve the package root regardless of the caller's working directory.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 1

# ── Select the stack ──────────────────────────────────────────────────────────
# Note every COMPOSE array passes -f explicitly, which suppresses the automatic
# merge of docker-compose.override.yml (the local Swagger port mappings). A
# deployed service is reachable only through Kong.
env_lc=$(printf '%s' "${DEPLOY_ENV:-}" | tr '[:upper:]' '[:lower:]')
case "$env_lc" in
  development)
    TEMPLATE=octopus/env.dev.template
    COMPOSE=(docker compose --profile dev -f docker-compose.yml -f octopus/docker-compose.deploy.yml)
    MIGRATE=(--profile migrate run --rm --no-deps migrate-dev)
    HEALTH_CONTAINERS=(fixmytext-account-svc fixmytext-ai-svc fixmytext-text-svc fixmytext-payments-svc fixmytext-kong)
    KONG_CONTAINER=fixmytext-kong
    PROBE_CONTAINER=fixmytext-account-svc
    # Dev bind-mounts package files (kong.yml); Octopus purges and re-extracts
    # the directory each deploy, so every mount points at a NEW inode. Compose
    # does not recreate containers for mounted-content changes, so without an
    # explicit recreate a redeploy would silently keep serving the old config.
    RECREATE_ALL=1
    ;;
  production)
    TEMPLATE=octopus/env.prod.template
    COMPOSE=(docker compose -f docker-compose-prod.yml)
    MIGRATE=(--profile migrate run --rm --no-deps migrate)
    HEALTH_CONTAINERS=(fixmytext-prod-account-svc fixmytext-prod-ai-svc fixmytext-prod-text-svc fixmytext-prod-payments-svc kong-prod)
    KONG_CONTAINER=kong-prod
    PROBE_CONTAINER=fixmytext-prod-account-svc
    # Prod services are self-contained images — compose restarts them only when
    # a rebuild actually produced a different image, so an unchanged redeploy is
    # zero-downtime. Only Kong bind-mounts a package file; it is recreated
    # explicitly below.
    RECREATE_ALL=0
    ;;
  *)
    echo "[deploy] ERROR: DEPLOY_ENV must be 'Development' or 'Production' (got '${DEPLOY_ENV:-<unset>}')" >&2
    exit 1
    ;;
esac
echo "[deploy] environment: ${DEPLOY_ENV} — template: ${TEMPLATE}"

# ── Render .env ───────────────────────────────────────────────────────────────
# Fail fast if a required Octopus variable was left unbound: Octostache leaves
# unmatched tokens in place, so any surviving "#{" means a variable is missing
# in Octopus. Safe to print — unbound lines still hold the token, not a value.
# (Only the selected template matters; the other environment's template will
# legitimately contain unbound tokens here.)
if grep -n '#{' "$TEMPLATE"; then
  echo "[deploy] ERROR: unbound Octopus variables above — define them as project variables scoped to the ${DEPLOY_ENV} environment (see docs/octopus-setup.md, Stage D)." >&2
  exit 1
fi
umask 077
cp "$TEMPLATE" .env
echo "[deploy] .env rendered ($(grep -c '=' .env) entries, mode 600)"

# velobits-proxy-net is created by the velobits-infra stack, which normally
# deploys first. Create it here too so deploy order can never hard-fail: this
# stack declares it `external`, and `up` aborts on a missing external network.
docker network inspect velobits-proxy-net >/dev/null 2>&1 || {
  echo "[deploy] creating shared external network velobits-proxy-net"
  docker network create velobits-proxy-net
}

# `config -q` validates the merged files — and, for the dev stack, catches
# docker compose < 2.24, which cannot parse the !override / !reset tags.
echo "[deploy] $(docker compose version)"
"${COMPOSE[@]}" config -q

# ── Build ─────────────────────────────────────────────────────────────────────
if [ ! -f .dockerignore ]; then
  echo "[deploy] WARNING: .dockerignore missing from package — build context will include the rendered .env" >&2
fi
echo "[deploy] building service images on this host (--pull refreshes base images;"
echo "[deploy] first build takes several minutes, cached afterwards)"
"${COMPOSE[@]}" build --pull
echo "[deploy] pulling pinned images (kong, redis, postgres)"
"${COMPOSE[@]}" pull --ignore-buildable --quiet

# ── Migrations ────────────────────────────────────────────────────────────────
# An explicit, gated step rather than a side effect of `up`: the deploy must
# fail here, before any new service container serves traffic, if the schema
# cannot be brought to head. account-svc owns auth.users and payments-svc keeps
# cross-schema FKs into it, so the container runs them in that order.
# --no-deps because the database is remote — there is nothing local to start.
echo "[deploy] running alembic migrations"
"${COMPOSE[@]}" "${MIGRATE[@]}"
echo "[deploy] migrations at head"

# ── Start ─────────────────────────────────────────────────────────────────────
echo "[deploy] starting stack"
if [ "$RECREATE_ALL" = "1" ]; then
  "${COMPOSE[@]}" up -d --remove-orphans --force-recreate
else
  "${COMPOSE[@]}" up -d --remove-orphans
  # Kong bind-mounts gateway/kong/kong.yml from the purged package directory.
  "${COMPOSE[@]}" up -d --force-recreate --no-deps kong
fi

# ── Health gates ──────────────────────────────────────────────────────────────
# Every service defines a container healthcheck, so gate on Docker's status.
# A green Octopus task therefore means the stack actually serves, not just that
# files were copied.
for container in "${HEALTH_CONTAINERS[@]}"; do
  echo "[deploy] waiting for ${container} to report healthy (max 300s)"
  deadline=$((SECONDS + 300))
  while :; do
    status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || echo missing)
    if [ "$status" = "healthy" ]; then
      break
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "[deploy] ERROR: ${container} is '$status' after 300s" >&2
      docker logs --tail 100 "$container" >&2 || true
      exit 1
    fi
    sleep 5
  done
  echo "[deploy] ${container} healthy"
done

# ── Smoke test ────────────────────────────────────────────────────────────────
# The health gates prove each container is up; this proves Kong actually
# ROUTES to one — a broken kong.yml still passes `kong health` while 404ing
# every request. Driven from a service container because python is guaranteed
# there and the Kong image has no dependable curl, and addressed as `kong`:
# the network alias compose publishes from the service name on both networks,
# so this needs no published port.
echo "[deploy] smoke-testing Kong routing (${PROBE_CONTAINER} -> kong:8000/health)"
probe='import urllib.request as u; u.urlopen("http://kong:8000/health", timeout=10).read()'
if ! docker exec "$PROBE_CONTAINER" python -c "$probe"; then
  echo "[deploy] ERROR: Kong did not route /health to a healthy upstream" >&2
  docker logs --tail 100 "$KONG_CONTAINER" >&2 || true
  exit 1
fi
echo "[deploy] Kong routing OK"

# Reclaim space from superseded image layers (dangling only — running images and
# pinned tags are untouched; each source change produces new service images).
docker image prune -f >/dev/null

echo "[deploy] done — stack is up:"
"${COMPOSE[@]}" ps
