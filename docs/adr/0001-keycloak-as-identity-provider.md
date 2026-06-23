# ADR 0001: Keycloak as identity provider

- **Status**: Accepted (2026-05-18)
- **Supersedes**: DIY HS256 issuance in `app/core/security.py`

## Context

The monolith ships its own auth flow: bcrypt password hashing
(`app/services/auth_service.py`), HS256 JWT issuance with a shared
`SECRET_KEY` (`app/core/security.py`), and SMTP delivery of verification /
password-reset emails (`app/services/email/`). As we split the monolith
into microservices, every service needs to verify user identity. Three
options:

1. **Keep DIY auth, share the SECRET_KEY across services.** Simplest, but
   the shared secret is a single point of compromise and rotation across
   multiple services is painful.
2. **Roll our own auth-svc.** Reuse existing bcrypt + HS256 code. Adds an
   extra service to maintain forever, and any future feature
   (MFA, social login, SSO, password policies) becomes our problem.
3. **Adopt a managed identity provider.** Keycloak, Authentik, Zitadel,
   Ory Kratos, FusionAuth, Supabase Auth, Clerk, WorkOS.

## Decision

Use **Keycloak** as the identity provider.

- **Tokens**: RS256, JWKS-distributed public keys. Services verify locally
  with cached public keys — no per-request roundtrip to Keycloak.
- **Storage**: Keycloak runs its own PostgreSQL (`keycloak-db` service in
  docker-compose), separate from the monolith's `db-service`.
- **Realms**: `Velobits-Dev` (dev) and `Velobits-Prod` (prod). Two clients per realm:
  `develop-fixmytext` / `fixmytext` (public, PKCE — frontend) and `fixmytext-backend`
  (confidential, service account for Admin API).
- **Migration path**: TODO — read `auth.users` from the monolith DB and
  push each row into Keycloak via the Admin API; bcrypt hashes are
  imported as opaque credentials so users keep their existing passwords.

## Why Keycloak (not the alternatives)

| Option | Rejected because |
|---|---|
| Authentik | Younger ecosystem; smaller community |
| Zitadel | Newer; less Java/Spring familiarity (we're on Python but ops mindshare matters) |
| Ory Kratos | Mature but lower-level — composes well with a separate hydra; more moving parts |
| FusionAuth | Closed core; paid features for SSO scenarios we may want later |
| Supabase Auth | Tied to Supabase ecosystem; harder to host in our own infra |
| Clerk / WorkOS | Hosted-SaaS pricing scales with MAU; vendor lock-in |

Keycloak wins for: mature SSO/OIDC support out of the box, free + self-hosted,
no per-user pricing, B2B-ready (organizations, SAML, social login, MFA) so
the FixMyText → VeloBits B2B evolution is a config change rather than a
re-platform.

## Consequences

**Positive:**
- Auth complexity moves out of our codebase. No more bcrypt, password
  policy, password-reset email flow, or token issuance to maintain.
- Frontend gets a real OIDC client (`develop-fixmytext` in dev, `fixmytext`
  in prod) with PKCE — industry-standard and immediately compatible with
  mobile SDKs if/when we add native apps.
- Future B2B features (SSO via Okta / Azure AD, SAML, social login) are
  config in the Keycloak admin console rather than code work.

**Negative:**
- One more service to operate (Keycloak + its Postgres).
- Memory cost: ~512 MB RAM for Keycloak + ~100 MB for its Postgres in dev.
- Learning curve for the Keycloak admin model (realms, clients, roles,
  client scopes).

**Neutral:**
- Migration cost is one-time (a future script).
- Production hardening (HA, TLS, external secret store) is TODO — aligned
  with the deployment milestone, not a current-iteration risk.

## Current status

Keycloak is the **sole, fully-active auth path**. All services verify
RS256 JWTs locally against the realm's JWKS (no DIY HS256 issuance remains
in the request path). `account-svc` owns the identity surface: registration
and login proxy to Keycloak, sessions are tracked via a host-only signed
cookie, and OIDC single-logout is handled by the `/auth/backchannel-logout`
endpoint that Keycloak calls server-to-server. The frontend authenticates
through the public PKCE client (`develop-fixmytext` dev / `fixmytext` prod)
and the backend authenticates to the Admin API via the `fixmytext-backend`
service account. SMTP, email verification, and password reset run through
Keycloak.

## Amendment (2026-06-23): service-account admin auth

`account-svc` now authenticates to the Keycloak Admin API using a dual
strategy (`app/services/keycloak_admin.py`, added in commit `c8d1539`):

- **Preferred** — dedicated service-account client (`fixmytext-backend`)
  via the `client_credentials` grant against the **product realm**'s token
  endpoint. Used when `KEYCLOAK_SERVICE_ACCOUNT_ID` and
  `KEYCLOAK_SERVICE_ACCOUNT_SECRET` are both set. The client is granted the
  `manage-users` / `view-users` roles from `realm-management` by
  `bootstrap.sh`, so it never needs master-realm credentials.
- **Fallback** — master-realm `admin-cli` `password` grant using
  `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD`. Used only when the service
  account is not yet provisioned.

Admin tokens are cached for their lifetime to avoid hammering the token
endpoint.
