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

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Create a new user account |
| POST | `/auth/login` | No | Login, receive JWT tokens |
| POST | `/auth/refresh` | Cookie | Refresh access token |
| POST | `/auth/logout` | Yes | End session |
| GET | `/auth/me` | Yes | Get current user info |

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

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/user-data/me` | Yes | User profile |
| GET | `/user-data/gamification` | Yes | XP, streaks, achievements |
| GET | `/user-data/settings` | Yes | User preferences |
| PATCH | `/user-data/settings` | Yes | Update preferences |

### History

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/history/` | Yes | Get operation history (paginated) |
| DELETE | `/history/{id}` | Yes | Soft-delete a history entry |

### Sharing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/share/` | No | Create a shareable link |
| GET | `/share/{id}` | No | Retrieve a shared result |

### Billing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/subscription/create-order` | Yes | Create Razorpay order |
| POST | `/subscription/webhook` | No* | Razorpay webhook (*HMAC verified) |
| GET | `/subscription/status` | Yes | Get subscription status |
| GET | `/passes/` | Yes | List available passes |
| POST | `/passes/purchase` | Yes | Purchase a prepaid pass |

## Rate Limits

| User Type | Limit |
|-----------|-------|
| Anonymous visitor | 3 uses per tool per day (fingerprint tracked) |
| Free tier (logged in) | 3 uses per tool per day |
| Premium subscriber | Unlimited |
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
