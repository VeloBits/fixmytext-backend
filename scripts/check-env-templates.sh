#!/usr/bin/env bash
# Validate the Octopus environment templates (octopus/env.*.template).
#
# Those templates are the ONLY source of a deployed .env: octopus/deploy.sh
# renders the selected one and copies it over. So a setting a service asserts at
# startup but the template omits does not fail at review time — it fails as a
# container that will not boot, mid-deploy. This script is that review.
#
# Run locally before pushing, or let CI run it (ci.yml, gateway job):
#   bash scripts/check-env-templates.sh
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 1

TEMPLATES=(octopus/env.dev.template octopus/env.prod.template)

# Every key both environments must define. Derived from the startup guards in
# services/*/main.py (assert_required_in_prod) plus the `${VAR:?}` requirements
# in docker-compose-prod.yml — keep this list in step with those.
REQUIRED=(
  ENVIRONMENT
  DATABASE_URL
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  REDIS_URL
  KEYCLOAK_URL
  KEYCLOAK_REALM
  KEYCLOAK_AUDIENCE
  KEYCLOAK_JWKS_URL
  KEYCLOAK_ISSUER
  SECRET_KEY
  SESSION_COOKIE_SECRET
  SESSION_COOKIE_SECURE
  INTERNAL_SHARED_SECRET
  TRUSTED_PROXY_HOSTS
  FRONTEND_URL
  ALLOWED_ORIGINS
  GROQ_API_KEY
  RAZORPAY_KEY_ID
  RAZORPAY_KEY_SECRET
  RAZORPAY_WEBHOOK_SECRET
)

fail=0
err() {
  # GitHub renders ::error:: as an annotation; harmless locally.
  echo "::error::$*" >&2
  fail=1
}

for tmpl in "${TEMPLATES[@]}"; do
  if [ ! -f "$tmpl" ]; then
    err "$tmpl is missing"
    continue
  fi

  for key in "${REQUIRED[@]}"; do
    grep -qE "^${key}=" "$tmpl" || err "$tmpl is missing ${key}"
  done

  # Wildcard proxy trust on a public host lets any caller spoof
  # X-Forwarded-For and walk past the per-IP rate limiter.
  if grep -qE '^TRUSTED_PROXY_HOSTS=[*]' "$tmpl"; then
    err "$tmpl sets TRUSTED_PROXY_HOSTS=* — unsafe anywhere but localhost"
  fi

  # `VAR=   # note` — for an EMPTY value docker compose's env_file parser keeps
  # the comment AS the value. This exact bug put "# empty = host-only" into the
  # session cookie's Domain attribute once already.
  if grep -nE '^[A-Za-z_][A-Za-z0-9_]*=[[:space:]]+#' "$tmpl"; then
    err "$tmpl (lines above): inline comment would be parsed as the value"
  fi

  # Deployed environments are HTTPS-only behind Traefik.
  grep -qE '^SESSION_COOKIE_SECURE=true' "$tmpl" ||
    err "$tmpl must set SESSION_COOKIE_SECURE=true"

  # An unresolved token means the variable is not defined in Octopus; deploy.sh
  # aborts on it at deploy time. Catching an obviously malformed token here is
  # cheaper. (Well-formed #{TOKEN} placeholders are expected and fine.)
  if grep -nE '#\{[^}]*$' "$tmpl"; then
    err "$tmpl (lines above): unterminated Octopus token"
  fi
done

# Production-only invariants: these are what make the startup guards fire.
grep -qE '^ENVIRONMENT=production' octopus/env.prod.template ||
  err "env.prod.template must set ENVIRONMENT=production (it enables every startup guard)"
grep -qE '^KEYCLOAK_ISSUER=https://' octopus/env.prod.template ||
  err "env.prod.template must set an https KEYCLOAK_ISSUER"

if [ "$fail" -eq 0 ]; then
  echo "env templates OK (${#TEMPLATES[@]} files, ${#REQUIRED[@]} required keys each)"
fi
exit "$fail"
