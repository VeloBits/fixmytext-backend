# Changelog

All notable changes to the FixMyText backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Email-verification banner flow: `POST /auth/resend-verification` (authenticated, per-user rate-limited) re-sends the Keycloak verification email; the first verification email is sent automatically at just-in-time provisioning (send-once gated via Redis `SETNX`); `GET /auth/me` re-syncs `is_email_verified` from a fresh Bearer claim so verifying mid-session clears the banner without waiting for the session cookie to expire
- account-svc environment configuration: `KEYCLOAK_SERVICE_ACCOUNT_ID` / `KEYCLOAK_SERVICE_ACCOUNT_SECRET` (service-account auth for the Keycloak Admin API), `SESSION_COOKIE_*` (name, secret, secure, max-age, domain), `TRUSTED_PROXY_HOSTS`, resend-verification rate-limit settings (`RESEND_VERIFICATION_RATE_LIMIT_*`), `BACKCHANNEL_SECRET`, and share/history limits (`SHARE_EXPIRE_DAYS`, `MAX_SHARE_TEXT_LENGTH`, `HISTORY_PREVIEW_MAX_LENGTH`)
- Optional shared-secret guard on `/auth/backchannel-logout` via the `X-Backchannel-Secret` header (constant-time comparison)
- Pagination on user-data and history list endpoints (`page`/`page_size` on templates, pipelines, and history; `limit`/`offset` on discovered-tools)
- Keycloak realm enhancements: `userProfileConfig`, front-channel logout disabled, brute-force protection, strengthened password policy, and a dedicated service account for Admin API calls

### Changed

- **Authentication is now exclusively Keycloak-hosted.** The realm's blocking email-verification requirement (`verifyEmail`) is disabled, so unverified users enter the app and are prompted by the in-app banner instead of Keycloak's interstitial. The social first-login "review profile" step is disabled (`update.profile.on.first.login=off`, applied via `bootstrap.sh`) so Google/GitHub users cannot edit username/email on first sign-in
- Keycloak realm redirect/logout config: the production `fixmytext` client now allows the `/app/auth/callback` and `/app/auth/silent-callback` redirect URIs the SPA actually uses (login would previously fail with "Invalid redirect_uri"); post-logout redirect now lands on `/app/` instead of `/app/login`; the `fixmytext-backend` client gained redirect URIs so Admin-API `send-verify-email` no longer fails
- Template listing now filters out soft-deleted rows (`is_deleted == false`)
- Share view counter is incremented atomically to avoid a read-modify-write race

### Removed

- **Gamification feature removed** (2026-07-13). `GET`/`PUT /user/gamification` are converted to authenticated, DB-free no-op stubs that return a static zero-state (each hit WARNING-logged as `stale_gamification_call`) so stale cached SPA bundles don't 404 — the stubs will be deleted in a later release once logs show zero hits. The `GamificationResponse`/`GamificationUpdate` schemas, the `UserGamification` ORM model, and the `User.gamification` relationship are deleted, and the `activity.user_gamification` table (plus its three indexes) is dropped in account-svc migration `0003` (data intentionally not restorable). The reward economy (spin wheel, daily-login bonus, streak rewards in payments-svc) is unaffected
- `POST /auth/register` endpoint and its Keycloak Admin-API user-creation path (`create_keycloak_user`, `_lookup_keycloak_user_by_email`) — account creation happens exclusively on Keycloak's hosted registration page, removing an unused, unauthenticated user-creation endpoint from the attack surface. Also removed the now-unused `KEYCLOAK_PASSWORD_MIN_LENGTH` setting and the per-IP registration rate limiter

## [1.0.0] - 2026-04-02

### Added

- 200+ text transformation endpoints across 14 categories (Case, Cleanup, Encoding, Lines, Ciphers, Developer, AI Writing, AI Content, Language, Generation, Hashing, Comparison, Utility, Escaping)
- AI-powered tools via Groq Llama 3.3 70B with YAKE keyword extraction fallback
- JWT authentication with short-lived access tokens (15 min) and refresh tokens (7 days)
- Free tier enforcement with 3 uses per tool per day via visitor fingerprinting
- Premium subscriptions and prepaid usage passes via Razorpay integration
- Razorpay webhook handler for payment event processing
- Regional pricing support with IP-based geolocation
- Gamification system with XP, streaks, achievements (JSONB), daily quests, and lucky spin
- Operation history with soft delete support
- Shareable result links (public access, no auth required)
- PostgreSQL 16 with pgvector extension and three schemas (auth, activity, billing)
- 21 ORM models with async SQLAlchemy and UUID primary keys
- 18 Alembic migration versions with automatic migration on startup
- AI endpoint rate limiting per user
- Request logging middleware for all API calls
- Health check endpoint (GET /health)
- Docker support with dev and prod profiles
- Multi-stage Dockerfile for production with non-root user
- Pydantic Settings for environment variable management and validation

---

## Release Template

Copy this block when preparing a new release:

## [X.Y.Z] - YYYY-MM-DD

### Added
-

### Changed
-

### Fixed
-

### Removed
-
