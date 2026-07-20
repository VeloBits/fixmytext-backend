# API Reference

> Complete endpoint reference for the FixMyText backend.

## Base URL

```
http://localhost:8000/api/v1
```

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** `GET /health` returns `{"status": "ok", "version": "0.1.0"}`

## Authentication

JWT-based authentication with access and refresh tokens.

### Flow

1. `POST /auth/login` with email + password
2. Receive `access_token` in response body + `refresh_token` as httpOnly cookie
3. Include `Authorization: Bearer <access_token>` in all authenticated requests
4. Access token expires in 15 minutes
5. Use `POST /auth/refresh` (sends cookie automatically) to get a new access token

## Request/Response Format

### Standard Text Request

```json
POST /api/v1/text/uppercase
Content-Type: application/json

{
  "text": "hello world"
}
```

- `text` field: required, 1-50,000 characters

### Standard Text Response

```json
{
  "original": "hello world",
  "result": "HELLO WORLD",
  "operation": "uppercase"
}
```

### Specialized Request Schemas

| Schema | Extra Fields | Used By |
|--------|-------------|---------|
| `CaesarRequest` | `shift` (int, 1-25, default 3) | Caesar cipher |
| `ToneRequest` | `tone` (formal/casual/friendly) | Tone change |
| `FormatRequest` | `format` (paragraph/bullets/paragraph-bullets/numbered/qna/table/tldr/headings) | Content formatting |
| `RailFenceRequest` | `rails` (int, 2-10, default 3) | Rail fence cipher |
| `KeyedCipherRequest` | `key` (str, 1-100 chars) | Vigenere, Playfair |
| `SubstitutionRequest` | `mapping` (str, exactly 26 chars — A-Z substitution alphabet) | Substitution cipher |
| `NthLineRequest` | `n` (int, 2-100, default 2), `offset` (int ≥ 0, default 0) | Every-Nth-line extraction |
| `PadRequest` | `align` (left/right/center, default left) | Pad lines |
| `TruncateRequest` | `max_length` (int, 5-1000, default 80) | Truncate lines |
| `WrapRequest` | `prefix` (str, max 100 chars), `suffix` (str, max 100 chars) | Wrap lines |
| `SplitJoinRequest` | `delimiter` (str, max 20 chars, default `,`) | Split to lines, Join lines |
| `FilterRequest` | `pattern` (str, 1-200 chars), `case_sensitive` (bool, default false), `use_regex` (bool, default false) | Filter lines, Remove lines |
| `TranslateRequest` | `target_language` (str, default "English") | Translate |

### Error Response

```json
{
  "detail": "Error message describing the issue"
}
```

## Endpoints

### Authentication

Served by `account-svc` under the `/auth` prefix. Login, token refresh, and
logout are handled by Keycloak (OIDC); `account-svc` only verifies tokens,
issues the per-app session cookie, and proxies registration.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Create a user via the Keycloak Admin API (IP rate-limited) |
| GET | `/auth/me` | Yes | Return current user profile + issue the `fixmytext_session` cookie |
| POST | `/auth/session/clear` | No | Clear the session cookie and revoke the session (logout) |
| POST | `/auth/backchannel-logout` | Special | Keycloak OIDC back-channel SLO hook (see below) |

**Session cookie.** `GET /auth/me` sets an HttpOnly, host-only
`fixmytext_session` cookie (HMAC-signed, `SESSION_COOKIE_MAX_AGE` default 7
days). Once set, the cookie authenticates subsequent requests; Bearer JWTs are
still accepted in parallel during the transition window.

**Backchannel logout.** `POST /auth/backchannel-logout` is called
server-to-server by Keycloak (`application/x-www-form-urlencoded`, `logout_token`
form field) and is excluded from the OpenAPI schema. The signed logout token is
verified (issuer + back-channel-logout event claim) and all of the subject's
sessions are revoked in Redis. When the optional `BACKCHANNEL_SECRET` is
configured, the request must also include a matching `X-Backchannel-Secret`
header (compared in constant time) or it is rejected with **400**. Returns
**200** on success, **400** on an invalid token/secret.

### Text Transformations

All endpoints: `POST /api/v1/text/{slug}` — accept `TextRequest`, return `TextResponse` (unless noted).

**Case Transformations:**

| Endpoint | Description |
|----------|-------------|
| `/text/uppercase` | Convert to UPPERCASE |
| `/text/lowercase` | Convert to lowercase |
| `/text/camel-case` | Convert to camelCase |
| `/text/snake-case` | Convert to snake_case |
| `/text/kebab-case` | Convert to kebab-case |
| `/text/title-case` | Convert to Title Case |
| `/text/sentence-case` | Convert to Sentence case |
| `/text/alternating-case` | Convert to aLtErNaTiNg CaSe |

**Encoding / Decoding:**

| Endpoint | Description |
|----------|-------------|
| `/text/base64-encode` | Encode to Base64 |
| `/text/base64-decode` | Decode from Base64 |
| `/text/url-encode` | URL-encode text |
| `/text/url-decode` | URL-decode text |
| `/text/hex-encode` | Encode to hexadecimal |
| `/text/morse-encode` | Encode to Morse code |

**Developer Tools:**

| Endpoint | Description |
|----------|-------------|
| `/text/format-json` | Prettify JSON |
| `/text/minify-json` | Minify JSON |
| `/text/csv-to-json` | Convert CSV to JSON |
| `/text/json-to-yaml` | Convert JSON to YAML |
| `/text/sql-insert-gen` | Generate SQL INSERT statements |

**Line Operations:**

| Endpoint | Description |
|----------|-------------|
| `/text/sort-lines-asc` | Sort lines A to Z |
| `/text/sort-lines-desc` | Sort lines Z to A |
| `/text/reverse-lines` | Reverse line order |
| `/text/shuffle-lines` | Randomize line order |
| `/text/remove-duplicates` | Remove duplicate lines |
| `/text/number-lines` | Add line numbers |

**Ciphers:**

| Endpoint | Description |
|----------|-------------|
| `/text/caesar-cipher` | Caesar cipher (CaesarRequest) |
| `/text/rot13` | ROT-13 |
| `/text/vigenere` | Vigenere cipher (KeyedCipherRequest) |
| `/text/atbash` | Atbash cipher |

**Text Cleanup:**

| Endpoint | Description |
|----------|-------------|
| `/text/remove-extra-spaces` | Normalize whitespace |
| `/text/strip-html` | Remove HTML tags |
| `/text/remove-accents` | Strip diacritics |
| `/text/remove-emoji` | Remove emoji characters |

**AI Writing:**

| Endpoint | Description |
|----------|-------------|
| `/text/fix-grammar` | AI grammar correction |
| `/text/paraphrase` | AI paraphrasing |
| `/text/summarize` | AI summarization |
| `/text/tone-change` | Change tone (ToneRequest) |

**AI Content:**

| Endpoint | Description |
|----------|-------------|
| `/text/generate-hashtags` | Generate hashtags |
| `/text/seo-titles` | Generate SEO titles |
| `/text/meta-descriptions` | Generate meta descriptions |
| `/text/blog-outline` | Generate blog outline |

> Full list of all 200+ endpoints available at http://localhost:8000/docs

### User Data

Served by `account-svc` under the `/user` prefix.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/user/preferences` | Yes | Theme, persona, skin |
| PUT | `/user/preferences` | Yes | Update preferences (partial) |
| GET | `/user/templates` | Yes | List saved templates (paginated) |
| POST | `/user/templates` | Yes | Create a template |
| PUT | `/user/templates/{id}` | Yes | Update a template |
| DELETE | `/user/templates/{id}` | Yes | Delete a template |
| GET | `/user/ui-settings` | Yes | Tool view, keybindings, panel sizes |
| PUT | `/user/ui-settings` | Yes | Update UI settings (partial) |
| GET | `/user/favorites` | Yes | List favorited tools (by sort order) |
| POST | `/user/favorites/{tool_id}` | Yes | Add a favorite (idempotent) |
| DELETE | `/user/favorites/{tool_id}` | Yes | Remove a favorite |
| GET | `/user/tool-stats` | Yes | Aggregated per-tool usage stats |
| GET | `/user/pipelines` | Yes | List active pipelines (paginated) |
| POST | `/user/pipelines` | Yes | Create a multi-step pipeline |
| PUT | `/user/pipelines/{id}` | Yes | Update a pipeline |
| DELETE | `/user/pipelines/{id}` | Yes | Soft-delete a pipeline (sets `is_active=false`) |
| GET | `/user/discovered-tools` | Yes | List discovered tools (paginated) |
| GET | `/user/spin-history` | Yes | 20 most recent lucky-spin entries |

**Pagination.** `/user/templates` and `/user/pipelines` accept `page`
(`Query(ge=1)`, default 1) and `page_size` (`Query(ge=1, le=100)`, default 25).
`/user/discovered-tools` instead uses `limit` (`Query(ge=1, le=500)`, default
200) and `offset` (`Query(ge=0)`, default 0), and returns a total `count`
unaffected by pagination. `/user/spin-history` is fixed at the latest 20 entries
(no pagination params).

**Template soft-delete.** `GET /user/templates` returns only rows with
`is_deleted == false`.

**Gamification (removed 2026-07-13).** The gamification feature was removed.
`GET`/`PUT /user/gamification` remain as *transitional no-op stubs*: both are
still authenticated, do not touch the database, and return a static zero-state.
They exist only so stale cached SPA bundles (pre-removal) don't get 404s; each
hit is WARNING-logged as `stale_gamification_call`, and the routes are
scheduled for removal once logs show zero hits. The backing table
`activity.user_gamification` was dropped in account-svc migration 0003.

### History

Served by `account-svc` under the `/history` prefix. Soft-deleted entries are
excluded from all reads.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/history` | Yes | List operation history, newest first (paginated) |
| POST | `/history` | Yes | Record a new operation |
| GET | `/history/stats/summary` | Yes | Per-tool counts + recent tools |
| GET | `/history/{id}` | Yes | Get a single entry |
| DELETE | `/history/{id}` | Yes | Soft-delete a single entry |
| DELETE | `/history` | Yes | Soft-delete all entries (bulk clear) |

`GET /history` accepts `page` (`Query(ge=1)`, default 1), `page_size`
(`Query(ge=1, le=100)`, default 25), and an optional `tool_id` filter
(`max_length=100`); the response includes `total`, `page`, `page_size`, and
`has_more`. On `POST /history`, `input_preview` / `output_preview` are truncated
to `HISTORY_PREVIEW_MAX_LENGTH` characters (config-driven, default 500).

### Sharing

Served by `account-svc` under the `/share` prefix.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/share` | Optional | Create a shareable link (anonymous allowed) |
| GET | `/share/{id}` | No | Retrieve a shared result |

On create, `output_text` is truncated to `MAX_SHARE_TEXT_LENGTH` characters
(config-driven, default 50,000). Shares expire after `SHARE_EXPIRE_DAYS`
(default 30); fetching an expired share returns **410 Gone**, and a malformed or
unknown ID returns **404**. Each successful fetch atomically increments the
share's view counter.

### Billing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/subscription/status` | Yes | Tier, usage, credit balance, Pro expiry (`pro_expires_at`, `pro_cancelled`) |
| POST | `/subscription/checkout` | Yes | Create Razorpay order for Pro (one-time 30-day purchase; renewal opens 7 days before expiry) |
| POST | `/subscription/verify` | Yes | Verify Pro payment signature and fulfil (may return `status: refunded`) |
| POST | `/subscription/cancel` | Yes | Cancel Pro — access continues until `access_until` (period end) |
| POST | `/subscription/webhook` | No* | Razorpay webhook (*HMAC verified) |
| GET | `/passes/catalog` | No | Passes + credit packs with regional pricing |
| GET | `/passes/active` | Yes | Active passes and per-pack credit balances |
| POST | `/passes/order` | Yes | Create Razorpay order for a pass (scoped passes require exactly `tools` tool_ids) |
| POST | `/passes/credit-order` | Yes | Create Razorpay order for a credit pack |
| POST | `/passes/verify` | Yes | Verify pass/credit payment and fulfil (may return `status: refunded`) |
| POST | `/passes/spin` | Yes | Weekly reward spin |
| GET | `/passes/referral-code` | Yes | Get/generate referral code |
| POST | `/passes/claim-referral` | Yes | Claim a referral code |

Fulfillment is exactly-once: the verify callback and the webhook converge on a
UNIQUE-keyed payment ledger. A **captured** payment whose order fails
validation (wrong amount/scope) is **automatically refunded** via the Razorpay
refund API and reported as `status: refunded`; signature failures are plain
400s with no refund. First purchase (pass, credit, or Pro) also grants a
one-time welcome credit gift (`WELCOME_GIFT_CREDITS`, default 10), surfaced in
the verify response as `welcome_gift` / `welcome_credits`.

## Rate Limits

| User Type | Limit |
|-----------|-------|
| Anonymous visitor | 3 uses per tool per day (fingerprint tracked) |
| Free tier (logged in) | 3 uses per tool per day (+1 daily login bonus) |
| Premium subscriber | Unlimited while `pro_expires_at` is in the future |
| Pass holder | Deducted from pass balance |
| AI endpoints | Additional per-user rate limiting |

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (missing or expired token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 422 | Validation error (wrong request format) |
| 429 | Too many requests — trial limit exceeded or rate limited |
| 500 | Internal server error |
