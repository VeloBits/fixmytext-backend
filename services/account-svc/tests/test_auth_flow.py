"""End-to-end auth flow tests for the dual-auth (cookie + Bearer) system.

Covers:
- Cookie issuance on GET /auth/me with Bearer
- Cookie-only authentication (no Bearer needed on subsequent requests)
- Cookie takes priority; tampered/expired cookie falls through to Bearer
- Session clear endpoint behaviour
- Response shape and subscription_tier default
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MOCK_TARGET = "app.core.deps.verify_jwt_raw"

# Use the same secret the test environment sets so sign/verify round-trips work.
_TEST_SECRET = os.environ.get("SECRET_KEY", "test-secret-key-at-least-32-characters")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    keycloak_id: uuid.UUID | None = None,
    email: str = "user@example.com",
    display_name: str = "Test User",
    is_active: bool = True,
    is_email_verified: bool = True,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.keycloak_id = keycloak_id or uuid.uuid4()
    user.email = email
    user.display_name = display_name
    user.is_active = is_active
    user.is_email_verified = is_email_verified
    return user


def _make_db(
    user: MagicMock | None, *, subscription_tier: str | None = None
) -> AsyncMock:
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=user)
    mock_db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=subscription_tier)
        )
    )
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    return mock_db


def _valid_payload(kc_id: uuid.UUID) -> dict:
    return {
        "sub": str(kc_id),
        "email": "user@example.com",
        "email_verified": True,
        "preferred_username": "testuser",
    }


def _build_cookie(
    kc_id: uuid.UUID,
    *,
    email: str = "user@example.com",
    max_age: int = 3600,
    secret: str = _TEST_SECRET,
) -> str:
    """Return a valid signed session cookie value."""
    from app.core.session_cookie import build_claims, sign_session

    claims = build_claims(
        sub=str(kc_id),
        email=email,
        email_verified=True,
        roles=["user"],
        max_age_seconds=max_age,
    )
    return sign_session(claims, secret)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cookie_auth_succeeds_without_bearer(async_client):
    """A valid signed session cookie is sufficient for authentication — no JWT
    JWKS call needed."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id)
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    with patch("app.core.deps.settings") as mock_settings:
        mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
        mock_settings.SESSION_COOKIE_SECRET = _TEST_SECRET
        cookie_value = _build_cookie(kc_id, secret=_TEST_SECRET)
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                cookies={"fixmytext_session": cookie_value},
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cookie_takes_priority_over_bearer(async_client):
    """When both a valid cookie AND a Bearer token are present, identity comes
    from the cookie: even a Bearer that FAILS verification cannot break the
    request. (/auth/me additionally peeks at a verifiable Bearer to re-sync
    claim-derived fields — see test_me_resyncs_email_verified_from_bearer.)"""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id)
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    cookie_value = _build_cookie(kc_id, secret=_TEST_SECRET)

    with patch("app.core.deps.settings") as mock_settings:
        mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
        mock_settings.SESSION_COOKIE_SECRET = _TEST_SECRET
        with patch(_MOCK_TARGET, side_effect=Exception("invalid token")):
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = await async_client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": "Bearer garbage.token.here"},
                    cookies={"fixmytext_session": cookie_value},
                )
                # Cookie authenticated the request; the unverifiable Bearer was
                # ignored (peek_bearer_claims returns None instead of raising).
                assert response.status_code == 200
            finally:
                app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_me_resyncs_email_verified_from_bearer(async_client):
    """A cookie-authenticated user whose DB row is stale gets is_email_verified
    re-synced from the fresh Bearer claim on /auth/me. The cookie path never
    re-reads Keycloak claims, so without this a user who verified their email
    mid-session would stay 'unverified' until the cookie expired (~7 days)."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id, is_email_verified=False)
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    cookie_value = _build_cookie(kc_id, secret=_TEST_SECRET)

    with patch("app.core.deps.settings") as mock_settings:
        mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
        mock_settings.SESSION_COOKIE_SECRET = _TEST_SECRET
        with patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)):
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = await async_client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": "Bearer fresh.silent-renew.token"},
                    cookies={"fixmytext_session": cookie_value},
                )
                assert response.status_code == 200
                assert response.json()["is_email_verified"] is True
                assert fake_user.is_email_verified is True
            finally:
                app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_tampered_cookie_falls_through_to_bearer(async_client):
    """A tampered cookie fails HMAC verification and the request falls through
    to the Bearer token, which succeeds → 200."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id)
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    good_cookie = _build_cookie(kc_id, secret=_TEST_SECRET)
    # Corrupt the HMAC signature (flip the last hex char)
    payload_part, sig = good_cookie.split(".", 1)
    flipped = "0" if sig[-1] != "0" else "1"
    tampered_cookie = f"{payload_part}.{sig[:-1]}{flipped}"

    with patch("app.core.deps.settings") as mock_settings:
        mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
        mock_settings.SESSION_COOKIE_SECRET = _TEST_SECRET
        with patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)):
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = await async_client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": "Bearer valid.fallback.token"},
                    cookies={"fixmytext_session": tampered_cookie},
                )
                assert response.status_code == 200
            finally:
                app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_expired_cookie_falls_through_to_bearer(async_client):
    """A cookie with an expired ``exp`` fails verify_session and the request
    falls through to the Bearer token → 200."""
    import time

    from app.core.session_cookie import sign_session
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id)
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    # Build a cookie with exp already in the past
    expired_claims = {
        "sub": str(kc_id),
        "email": "user@example.com",
        "email_verified": True,
        "roles": ["user"],
        "iat": int(time.time()) - 7200,
        "exp": int(time.time()) - 3600,  # expired 1 hour ago
    }
    expired_cookie = sign_session(expired_claims, _TEST_SECRET)

    with patch("app.core.deps.settings") as mock_settings:
        mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
        mock_settings.SESSION_COOKIE_SECRET = _TEST_SECRET
        with patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)):
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = await async_client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": "Bearer valid.fallback.token"},
                    cookies={"fixmytext_session": expired_cookie},
                )
                assert response.status_code == 200
            finally:
                app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cookie_with_invalid_sub_uuid_falls_through(async_client):
    """A session cookie whose ``sub`` is not a valid UUID is skipped and the
    request falls through to the Bearer token → 200."""
    from app.core.session_cookie import build_claims, sign_session
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id)
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    # Cookie with a non-UUID sub — passes HMAC verification but UUID() will fail
    bad_sub_claims = build_claims(
        sub="not-a-uuid",
        email="user@example.com",
        email_verified=True,
        roles=["user"],
        max_age_seconds=3600,
    )
    bad_sub_cookie = sign_session(bad_sub_claims, _TEST_SECRET)

    with patch("app.core.deps.settings") as mock_settings:
        mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
        mock_settings.SESSION_COOKIE_SECRET = _TEST_SECRET
        with patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)):
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = await async_client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": "Bearer valid.fallback.token"},
                    cookies={"fixmytext_session": bad_sub_cookie},
                )
                assert response.status_code == 200
            finally:
                app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_session_clear_deletes_cookie(async_client):
    """POST /auth/session/clear → 204 and the response expires the cookie
    (Max-Age=0 or past Expires)."""
    response = await async_client.post("/api/v1/auth/session/clear")
    assert response.status_code == 204
    set_cookie = response.headers.get("set-cookie", "")
    assert "fixmytext_session=" in set_cookie.lower()
    assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()


@pytest.mark.asyncio
async def test_session_clear_requires_no_auth(async_client):
    """POST /auth/session/clear succeeds with no token and no cookie → 204.

    The endpoint is intentionally unprotected: clearing a cookie is idempotent
    and the worst a hostile caller can do is log themselves out.
    """
    response = await async_client.post("/api/v1/auth/session/clear")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_get_me_response_shape(async_client):
    """GET /auth/me response JSON must contain the documented fields."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(
        keycloak_id=kc_id,
        email="shape@example.com",
        display_name="Shape Tester",
        is_email_verified=True,
    )
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "email" in data
            assert "display_name" in data
            assert "subscription_tier" in data
            assert "is_email_verified" in data
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_me_subscription_tier_db_exception_defaults_to_free(async_client):
    """T4: If the subscription-tier DB query raises, ``_get_subscription_tier``
    catches the exception and returns ``"free"`` instead of propagating a 500.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id)

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=fake_user)
    # Subscription tier lookup raises
    mock_db.execute = AsyncMock(side_effect=SQLAlchemyError("db down"))
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            # DB error is caught by _get_subscription_tier and returns "free"
            assert response.status_code == 200
            assert response.json()["subscription_tier"] == "free"
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_me_cookie_value_is_validly_signed(async_client):
    """T10: The Set-Cookie value after GET /auth/me is a valid signed cookie.

    Verifies that the cookie isn't just present in the header (checked by
    test_get_me_sets_session_cookie) but also that verify_session can decode it
    and the claims match the authenticated user.
    """
    from app.core.session_cookie import verify_session
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id, email="cookie-verify@example.com")
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    with (
        patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)),
        patch("app.api.v1.endpoints.auth.settings") as mock_settings,
    ):
        mock_settings.SESSION_COOKIE_SECRET = _TEST_SECRET
        mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
        mock_settings.SESSION_COOKIE_MAX_AGE = 3600
        mock_settings.SESSION_COOKIE_SECURE = False
        mock_settings.SESSION_COOKIE_DOMAIN = ""
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 200
            set_cookie = response.headers.get("set-cookie", "")
            assert "fixmytext_session=" in set_cookie
            # Extract the raw cookie value and verify it cryptographically
            cookie_value = set_cookie.split("fixmytext_session=", 1)[1].split(";", 1)[0]
            claims = verify_session(cookie_value, _TEST_SECRET)
            assert claims is not None
            assert claims["sub"] == str(kc_id)
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_me_subscription_tier_defaults_to_free(async_client):
    """When there is no active subscription row, ``subscription_tier`` is ``"free"``."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id)
    # Pass subscription_tier=None → _get_subscription_tier returns "free"
    mock_db = _make_db(fake_user, subscription_tier=None)

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["subscription_tier"] == "free"
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_me_response_has_cache_control_no_store(async_client):
    """GET /auth/me must include Cache-Control: no-store so proxies and CDNs
    never cache the response and silently drop the Set-Cookie header."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id)
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=_valid_payload(kc_id)):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 200
            assert response.headers.get("cache-control") == "no-store"
        finally:
            app.dependency_overrides.clear()
