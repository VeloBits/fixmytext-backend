# ADR 0005: JWKS + RS256 JWT verification (with HS256 transition adapter)

- **Status**: Accepted (2026-05-18)

## Context

The monolith currently issues HS256 JWTs signed with a shared
`SECRET_KEY` (`app/core/security.py`). After the auth cutover, Keycloak
will issue RS256 JWTs with public keys distributed via JWKS at
`http://keycloak:8080/realms/fixmytext/protocol/openid-connect/certs`.

Every service (monolith + extracted services) needs to verify incoming
user JWTs **independently** — no per-request roundtrip to a central
auth service. The verification mechanism must:

1. Work locally (no network call on the request hot path).
2. Handle Keycloak's key rotation without manual intervention.
3. Coexist with the legacy HS256 issuer during the transition.
4. Be shareable across services (one implementation, every service
   imports it).

## Decision

Adopt **RS256 + JWKS** as the long-term verification mechanism, with a
**dispatcher** in `fixmytext_shared.security.jwt.verify_jwt()` that routes
to the right adapter based on the `JWT_ALGORITHM` env var.

```python
from fixmytext_shared.security.jwt import verify_jwt

# Transition: HS256 with the monolith's SECRET_KEY
claims = verify_jwt(token, algorithm="HS256", secret=settings.SECRET_KEY)

# Post-cutover: RS256 via JWKS, no shared secret
claims = verify_jwt(
    token,
    algorithm="RS256",
    jwks_url=settings.KEYCLOAK_JWKS_URL,
    audience=settings.KEYCLOAK_AUDIENCE,
)
```

Both adapters return a `ClaimSchema` dataclass with typed fields: `sub`,
`exp`, `iat`, `type`, `email`, `email_verified`, `roles`, `org_id`,
`iss`, `aud`. The `org_id` field is the **B2B-ready hook** — present
today, nullable, populated later when organisation tables exist.

### JWKS cache

The `jwks` adapter uses PyJWT's `PyJWKClient` wrapped in an in-process
TTL cache (`cachetools.TTLCache`, 10-min TTL, max 8 distinct JWKS URLs).
On a `kid` cache-miss (Keycloak rotated keys), the cache is dropped and
a fresh fetch is forced once before failing.

## Why RS256 + JWKS (not the alternatives)

| Option | Rejected because |
|---|---|
| Token introspection (`POST /auth/verify`) | Adds a network roundtrip to every authenticated request; makes auth-svc / Keycloak critical path for every API call. |
| Shared HS256 secret across services | Single point of compromise; rotating the secret across multiple services is painful. |
| Kafka or other event-driven auth | Async messaging is the wrong abstraction for synchronous request validation. |
| Shared Redis session store | Adds Redis to the hot path; loses JWT's stateless benefit; per-request lookup. |
| Service mesh (Istio / Linkerd sidecar) | Massive ops overhead for a single-dev project. Premature until we have 10+ services in production. |

RS256 + JWKS is the industry default for greenfield microservices with
an OIDC-compliant identity provider. It's what every Keycloak / Auth0 /
Okta tutorial recommends.

## The HS256 transition adapter

The shared `verify_jwt()` dispatcher also exposes an HS256 path. It's
active today (because the monolith still issues HS256 tokens) and will
be deactivated by flipping `JWT_ALGORITHM=HS256` → `RS256` in the
monolith's env once Keycloak takes over issuance.

The dispatcher exists primarily so the transition is a one-line env
change rather than a code refactor. After the auth cutover, the HS256
adapter is still importable but no service has `JWT_ALGORITHM=HS256` in
its env.

## Token revocation (the classic JWT pain point)

The current design does **not** address revocation. RS256 tokens are
still bearer tokens with a short lifespan (5 min access; 30 days refresh).
If a user account is compromised in the 5-min window between revocation
and expiry, the attacker keeps access until expiry.

If this becomes a real concern (TODO, depending on threat model):
- Publish `TOKEN_REVOKED` events via Redis pub/sub
- Each service maintains a small in-memory set of revoked `jti` claims
  to check during decode
- Add a `jti` claim to issued tokens (Keycloak configurable)

This is composable with the dispatcher — no architectural change needed.

## Consequences

**Positive:**
- No shared secret across services. Every service can verify tokens
  without holding a signing key.
- Keycloak key rotation is handled transparently via JWKS cache miss +
  forced refresh.
- The dispatcher pattern means the RS256 cutover is a one-line
  env change.
- `ClaimSchema` is forward-compatible with B2B claims (`org_id`,
  expanded `roles`).

**Negative:**
- Slightly more code than a simple `decode_token()` function. Mitigated:
  the dispatcher is ~60 lines; the adapters are ~30 lines each;
  the test suite covers both adapters.
- JWKS fetch on cold start adds ~50ms to the first request after a
  service starts. Mitigated: warm-up the cache during service startup
  if/when this becomes a measurable issue.

**Neutral:**
- The JWKS adapter is registered but inactive on the current code path.
  It exists for code locality (so the dispatcher works) but the hot path
  doesn't hit it until the auth cutover lands.
