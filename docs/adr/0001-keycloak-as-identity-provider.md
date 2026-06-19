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
- Frontend gets a real OIDC client (`fixmytext-frontend`) with PKCE —
  industry-standard and immediately compatible with mobile SDKs if/when we
  add native apps.
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

Keycloak is started by docker-compose and the realm is auto-imported, but
**no users are provisioned and no traffic flows through it**. Activation
is TODO (user migration script, JWT_ALGORITHM flip, frontend OIDC,
Kong route to Keycloak, SMTP wiring).
