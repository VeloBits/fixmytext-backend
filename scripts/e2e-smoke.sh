#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# e2e-smoke.sh - Automated endpoint smoke test for the FixMyText dev stack.
#
# Usage:
#   TEST_USER=you@example.com TEST_PW=YourPass ./scripts/e2e-smoke.sh
#
# Prerequisites:
#   - docker compose --profile dev is either already up or will be started
#   - jq installed  (brew install jq / apt install jq)
#   - The Keycloak realm 'fixmytext' is imported and SMTP is optional
#   - TEST_USER is a registered Keycloak user (register via the frontend first)
#
# What this script does:
#   1. Starts the dev stack if containers aren't already running
#   2. Waits for all services to be healthy
#   3. Acquires a Keycloak JWT via Direct Grant
#   4. Hits every major endpoint and asserts the expected HTTP status
#   5. Prints a PASS/FAIL checklist
#
# Exit code: 0 if all tests pass, 1 if any fail.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

KONG="http://localhost:8000"
KEYCLOAK="http://localhost:8080"
REALM="fixmytext"
CLIENT_ID="fixmytext-frontend"

# Colour helpers
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

log_pass() { echo -e "${GREEN}  PASS${NC}  $1"; PASS=$((PASS+1)); }
log_fail() { echo -e "${RED}  FAIL${NC}  $1  (got: $2, expected: $3)"; FAIL=$((FAIL+1)); }
log_skip() { echo -e "${YELLOW}  SKIP${NC}  $1  ($2)"; SKIP=$((SKIP+1)); }

# ── 1. Start dev stack if not running ────────────────────────────────────────

echo "=== Checking dev stack ==="
if ! docker compose --profile dev ps --services --filter status=running 2>/dev/null | grep -q kong; then
  echo "Starting dev stack (this may take ~90 seconds)..."
  docker compose --profile dev up --build -d
fi

# ── 2. Wait for Kong + account-svc to be ready ───────────────────────────────

echo "=== Waiting for Kong to be ready ==="
ELAPSED=0
TIMEOUT=120
until docker inspect -f '{{.State.Health.Status}}' fixmytext-kong 2>/dev/null | grep -q healthy; do
  if [ "$ELAPSED" -ge "$TIMEOUT" ]; then echo "Kong TIMEOUT"; break; fi
  echo "  waiting for Kong... (${ELAPSED}s)"; sleep 5; ELAPSED=$((ELAPSED+5))
done
echo "  Kong: $(docker inspect -f '{{.State.Health.Status}}' fixmytext-kong 2>/dev/null)"

echo "=== Waiting for account-svc to be ready ==="
ELAPSED=0
until docker inspect -f '{{.State.Health.Status}}' fixmytext-account-svc 2>/dev/null | grep -q healthy; do
  if [ "$ELAPSED" -ge "$TIMEOUT" ]; then echo "account-svc TIMEOUT"; break; fi
  echo "  waiting for account-svc... (${ELAPSED}s)"; sleep 5; ELAPSED=$((ELAPSED+5))
done
echo "  account-svc: $(docker inspect -f '{{.State.Health.Status}}' fixmytext-account-svc 2>/dev/null)"

# ── 3. Acquire access token ───────────────────────────────────────────────────

echo ""
echo "=== Acquiring Keycloak token ==="

TEST_USER="${TEST_USER:-}"
TEST_PW="${TEST_PW:-}"

if [ -z "$TEST_USER" ] || [ -z "$TEST_PW" ]; then
  echo "  TEST_USER / TEST_PW not set - skipping authenticated endpoint tests."
  echo "  Set TEST_USER=you@example.com TEST_PW=yourpass to test auth-gated endpoints."
  TOKEN=""
else
  # Use --data-urlencode so credentials with special characters are safely
  # percent-encoded (prevents word-splitting / form injection).
  TOKEN=$(curl -sS -X POST \
    "${KEYCLOAK}/realms/${REALM}/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "grant_type=password" \
    --data-urlencode "client_id=${CLIENT_ID}" \
    --data-urlencode "username=${TEST_USER}" \
    --data-urlencode "password=${TEST_PW}" \
    --data-urlencode "scope=openid email profile" \
    2>/dev/null | jq -r '.access_token // empty' 2>/dev/null || echo "")
  if [ -z "$TOKEN" ]; then
    echo "  WARNING: Failed to acquire token - authenticated tests will be skipped."
    echo "  Make sure TEST_USER is registered in Keycloak at ${KEYCLOAK}/realms/${REALM}"
  else
    echo "  Token acquired (first 20 chars): ${TOKEN:0:20}..."
  fi
fi

AUTH_HEADER=""
[ -n "$TOKEN" ] && AUTH_HEADER="Authorization: Bearer ${TOKEN}"

# ── 4. Helper to assert HTTP status ──────────────────────────────────────────

check() {
  local label="$1"
  local method="$2"
  local url="$3"
  local expected="$4"
  local data="${5:-}"
  local need_auth="${6:-no}"

  if [ "$need_auth" = "yes" ] && [ -z "$TOKEN" ]; then
    log_skip "$label" "no token"
    return
  fi

  local args=("-s" "-o" "/dev/null" "-w" "%{http_code}" "-X" "$method" "$url")
  [ -n "$AUTH_HEADER" ] && args+=("-H" "$AUTH_HEADER")
  [ -n "$data" ] && args+=("-H" "Content-Type: application/json" "-d" "$data")

  local got
  got=$(curl "${args[@]}" 2>/dev/null)

  if [ "$got" = "$expected" ]; then
    log_pass "$label"
  else
    log_fail "$label" "$got" "$expected"
  fi
}

# ── 5. Endpoint tests ─────────────────────────────────────────────────────────

echo ""
echo "=== Infrastructure ==="
check "GET /health (via Kong)"               GET "${KONG}/health"         200
check "GET /health/ready (via Kong)"         GET "${KONG}/health/ready"   200
check "Keycloak realm discovery"             GET "${KEYCLOAK}/realms/${REALM}/.well-known/openid-configuration" 200

echo ""
echo "=== text-svc - local text tools ==="
check "POST /api/v1/text/uppercase"          POST "${KONG}/api/v1/text/uppercase"      200  '{"text":"hello world"}'
check "POST /api/v1/text/lowercase"          POST "${KONG}/api/v1/text/lowercase"      200  '{"text":"HELLO WORLD"}'
check "POST /api/v1/text/reverse"            POST "${KONG}/api/v1/text/reverse"        200  '{"text":"hello"}'
check "POST /api/v1/text/caesar-cipher"      POST "${KONG}/api/v1/text/caesar-cipher"  200  '{"text":"abc","shift":1}'
check "POST /api/v1/text/base64-encode"      POST "${KONG}/api/v1/text/base64-encode"  200  '{"text":"hello"}'
check "POST /api/v1/text/nonexistent-tool"   POST "${KONG}/api/v1/text/nonexistent"    404  '{"text":"x"}'

echo ""
echo "=== ai-svc - AI tools (auth required) ==="
check "POST /api/v1/ai/generate-hashtags (no auth → 401)" POST "${KONG}/api/v1/ai/generate-hashtags" 401 '{"text":"test"}'
check "POST /api/v1/ai/generate-hashtags (with auth)"     POST "${KONG}/api/v1/ai/generate-hashtags" 200 '{"text":"A text about software engineering"}' yes
check "POST /api/v1/ai/nonexistent-tool (with auth → 404)" POST "${KONG}/api/v1/ai/nonexistent" 404 '{"text":"x"}' yes

echo ""
echo "=== payments-svc - passes & subscription ==="
check "GET /api/v1/passes/catalog (public)"             GET  "${KONG}/api/v1/passes/catalog"            200
check "GET /api/v1/passes/active (no auth → 401)"       GET  "${KONG}/api/v1/passes/active"             401
check "GET /api/v1/passes/active (with auth)"           GET  "${KONG}/api/v1/passes/active"             200  "" yes
check "GET /api/v1/passes/referral-code (with auth)"    GET  "${KONG}/api/v1/passes/referral-code"      200  "" yes
check "GET /api/v1/subscription/status (no auth → 401)" GET  "${KONG}/api/v1/subscription/status"       401
check "GET /api/v1/subscription/status (with auth)"     GET  "${KONG}/api/v1/subscription/status"       200  "" yes

echo ""
echo "=== account-svc - user data, history, share, auth ==="
check "GET /api/v1/auth/me (no auth → 401)"             GET  "${KONG}/api/v1/auth/me"                   401
check "GET /api/v1/auth/me (with auth)"                  GET  "${KONG}/api/v1/auth/me"                   200  "" yes
check "GET /api/v1/user/preferences (no auth → 401)"    GET  "${KONG}/api/v1/user/preferences"          401
check "GET /api/v1/user/preferences (with auth)"         GET  "${KONG}/api/v1/user/preferences"          200  "" yes
check "GET /api/v1/user/gamification (with auth)"        GET  "${KONG}/api/v1/user/gamification"         200  "" yes
check "GET /api/v1/user/ui-settings (with auth)"         GET  "${KONG}/api/v1/user/ui-settings"          200  "" yes
check "GET /api/v1/user/templates (with auth)"           GET  "${KONG}/api/v1/user/templates"            200  "" yes
check "GET /api/v1/user/favorites (with auth)"           GET  "${KONG}/api/v1/user/favorites"            200  "" yes
check "GET /api/v1/user/tool-stats (with auth)"          GET  "${KONG}/api/v1/user/tool-stats"           200  "" yes
check "GET /api/v1/user/pipelines (with auth)"           GET  "${KONG}/api/v1/user/pipelines"            200  "" yes
check "GET /api/v1/user/discovered-tools (with auth)"    GET  "${KONG}/api/v1/user/discovered-tools"     200  "" yes
check "GET /api/v1/history (no auth → 401)"             GET  "${KONG}/api/v1/history"                   401
check "GET /api/v1/history (with auth)"                  GET  "${KONG}/api/v1/history"                   200  "" yes
check "GET /api/v1/history/stats/summary (with auth)"    GET  "${KONG}/api/v1/history/stats/summary"     200  "" yes
check "GET /api/v1/share/nonexistent (404)"             GET  "${KONG}/api/v1/share/nonexistent-id"      404

echo ""
echo "=== Keycloak JWKS (RS256 verification) ==="
check "GET Keycloak JWKS endpoint"  GET "${KEYCLOAK}/realms/${REALM}/protocol/openid-connect/certs" 200

# ── 6. Summary ───────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════"
echo -e "  ${GREEN}PASS${NC}: $PASS   ${RED}FAIL${NC}: $FAIL   ${YELLOW}SKIP${NC}: $SKIP"
echo "═══════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "❌ $FAIL test(s) failed - investigate before merging to main."
  exit 1
else
  echo ""
  echo "✅ All tests passed!"
  exit 0
fi
