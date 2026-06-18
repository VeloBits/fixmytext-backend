"""Tests for JWT validation in the ``get_current_user`` dependency.

Each test exercises a distinct JWT failure mode against ``GET /api/v1/auth/me``
using ``app.core.deps.verify_jwt_raw`` as the mock target — that is the name
bound in the deps module after ``from fixmytext_shared.security.jwt import
verify_jwt_raw``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt.exceptions
import pytest

_MOCK_TARGET = "app.core.deps.verify_jwt_raw"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    keycloak_id: uuid.UUID | None = None,
    email: str = "user@example.com",
    is_active: bool = True,
    is_email_verified: bool = True,
) -> MagicMock:
    """Return a minimal mock User ORM object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.keycloak_id = keycloak_id or uuid.uuid4()
    user.email = email
    user.display_name = "Test User"
    user.is_active = is_active
    user.is_email_verified = is_email_verified
    return user


def _valid_payload(keycloak_id: uuid.UUID | None = None) -> dict:
    """Return a minimal valid JWT payload dict."""
    return {
        "sub": str(keycloak_id or uuid.uuid4()),
        "email": "user@example.com",
        "email_verified": True,
        "preferred_username": "testuser",
    }


def _make_db(user: MagicMock | None) -> AsyncMock:
    """Return an async DB mock whose scalar() returns *user*."""
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=user)
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="free")))
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    return mock_db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_bearer_token_returns_200(async_client):
    """A well-formed Bearer token that passes JWKS verification → 200."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    payload = _valid_payload(kc_id)
    fake_user = _make_user(keycloak_id=kc_id)
    mock_db = _make_db(fake_user)

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=payload):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_expired_token_returns_401(async_client):
    """Bearer token that raises ExpiredSignatureError → 401."""
    from app.db.session import get_db
    from main import app

    async def override_get_db():
        yield _make_db(None)

    with patch(_MOCK_TARGET, side_effect=jwt.exceptions.ExpiredSignatureError("expired")):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer expired.jwt.token"},
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(async_client):
    """Bearer token that raises InvalidSignatureError → 401."""
    from app.db.session import get_db
    from main import app

    async def override_get_db():
        yield _make_db(None)

    with patch(_MOCK_TARGET, side_effect=jwt.exceptions.InvalidSignatureError("bad sig")):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer bad.signature.token"},
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_wrong_audience_returns_401(async_client):
    """Bearer token that raises InvalidAudienceError → 401."""
    from app.db.session import get_db
    from main import app

    async def override_get_db():
        yield _make_db(None)

    with patch(_MOCK_TARGET, side_effect=jwt.exceptions.InvalidAudienceError("bad aud")):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer wrong-audience.jwt.token"},
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_no_token_no_cookie_returns_401(async_client):
    """Request with no Authorization header and no cookie → 401."""
    from app.db.session import get_db
    from main import app

    async def override_get_db():
        yield _make_db(None)

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = await async_client.get("/api/v1/auth/me")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_malformed_bearer_returns_401(async_client):
    """Bearer token that raises ValueError (malformed JWT) → 401."""
    from app.db.session import get_db
    from main import app

    async def override_get_db():
        yield _make_db(None)

    with patch(_MOCK_TARGET, side_effect=ValueError("not a jwt")):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer not-a-jwt"},
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_inactive_user_returns_401(async_client):
    """Valid token but DB returns a user with is_active=False → 401."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    payload = _valid_payload(kc_id)
    # User exists but is inactive
    inactive_user = _make_user(keycloak_id=kc_id, is_active=False)
    mock_db = _make_db(inactive_user)

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=payload):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bearer_token_sub_as_integer_returns_401(async_client):
    """T9: JWT payload with an integer ``sub`` → 401.

    ``uuid.UUID(12345)`` raises TypeError; the caller must not get a 500.
    """
    from app.db.session import get_db
    from main import app

    int_sub_payload = {
        "sub": 12345,
        "email": "user@example.com",
        "email_verified": True,
    }

    async def override_get_db():
        yield _make_db(None)

    with patch(_MOCK_TARGET, return_value=int_sub_payload):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer int-sub.token"},
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bearer_token_sub_must_be_valid_uuid(async_client):
    """JWT payload with a non-UUID sub → 401 (UUID() constructor fails)."""
    from app.db.session import get_db
    from main import app

    bad_payload = {
        "sub": "not-a-uuid",
        "email": "user@example.com",
        "email_verified": True,
    }

    async def override_get_db():
        yield _make_db(None)

    with patch(_MOCK_TARGET, return_value=bad_payload):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid.sub.token"},
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()
