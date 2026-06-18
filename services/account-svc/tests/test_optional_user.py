"""Tests for the ``get_optional_user`` dependency.

``get_optional_user`` is used by all share endpoints. It returns a User ORM
object when a valid session cookie or Bearer JWT is present, and None
(not a 401) when auth is absent or invalid.

Mock targets: ``app.core.deps.verify_jwt_raw``, ``app.core.deps.settings``
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jwt.exceptions import PyJWTError

_MOCK_JWT = "app.core.deps.verify_jwt_raw"
_MOCK_SETTINGS = "app.core.deps.settings"
_TEST_SECRET = os.environ.get("SECRET_KEY", "test-secret-key-at-least-32-characters")


def _make_user(
    *,
    keycloak_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.keycloak_id = keycloak_id or uuid.uuid4()
    user.email = "user@example.com"
    user.display_name = "Test User"
    user.is_active = is_active
    user.is_email_verified = True
    return user


def _mock_settings(*, cookie_secret: str = "", cookie_name: str = "fixmytext_session") -> MagicMock:
    s = MagicMock()
    s.SESSION_COOKIE_NAME = cookie_name
    s.SESSION_COOKIE_SECRET = cookie_secret
    s.KEYCLOAK_JWKS_URL = "http://kc/certs"
    s.KEYCLOAK_AUDIENCE = "fixmytext-backend"
    s.KEYCLOAK_ISSUER = ""
    return s


def _build_cookie(kc_id: uuid.UUID, *, secret: str = _TEST_SECRET) -> str:
    from app.core.session_cookie import build_claims, sign_session

    claims = build_claims(
        sub=str(kc_id),
        email="user@example.com",
        email_verified=True,
        roles=["user"],
        max_age_seconds=3600,
    )
    return sign_session(claims, secret)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_auth_returns_none():
    """No credentials and no cookie → None (not 401)."""
    from app.core.deps import get_optional_user

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)

    request = MagicMock()
    request.cookies = {}

    with patch(_MOCK_SETTINGS, _mock_settings()):
        result = await get_optional_user(
            request=request, credentials=None, db=mock_db
        )
    assert result is None
    mock_db.scalar.assert_not_called()


@pytest.mark.asyncio
async def test_valid_bearer_returns_user():
    """Valid Bearer JWT → returns the corresponding User object."""
    from app.core.deps import get_optional_user

    from fastapi.security import HTTPAuthorizationCredentials

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id, is_active=True)
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=fake_user)

    request = MagicMock()
    request.cookies = {}
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")

    payload = {"sub": str(kc_id), "email": "user@example.com"}

    with patch(_MOCK_SETTINGS, _mock_settings()):
        with patch(_MOCK_JWT, return_value=payload):
            result = await get_optional_user(
                request=request, credentials=creds, db=mock_db
            )
    assert result is fake_user


@pytest.mark.asyncio
async def test_valid_cookie_returns_user():
    """Valid signed session cookie → returns the corresponding User object."""
    from app.core.deps import get_optional_user

    kc_id = uuid.uuid4()
    fake_user = _make_user(keycloak_id=kc_id, is_active=True)
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=fake_user)

    cookie_value = _build_cookie(kc_id, secret=_TEST_SECRET)
    request = MagicMock()
    request.cookies = {"fixmytext_session": cookie_value}

    with patch(_MOCK_SETTINGS, _mock_settings(cookie_secret=_TEST_SECRET)):
        result = await get_optional_user(
            request=request, credentials=None, db=mock_db
        )
    assert result is fake_user


@pytest.mark.asyncio
async def test_inactive_user_returns_none():
    """Auth succeeds but user.is_active is False → returns None (never raises)."""
    from app.core.deps import get_optional_user

    from fastapi.security import HTTPAuthorizationCredentials

    kc_id = uuid.uuid4()
    inactive_user = _make_user(keycloak_id=kc_id, is_active=False)
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=inactive_user)

    request = MagicMock()
    request.cookies = {}
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")
    payload = {"sub": str(kc_id), "email": "user@example.com"}

    with patch(_MOCK_SETTINGS, _mock_settings()):
        with patch(_MOCK_JWT, return_value=payload):
            result = await get_optional_user(
                request=request, credentials=creds, db=mock_db
            )
    assert result is None


@pytest.mark.asyncio
async def test_invalid_token_returns_none():
    """Malformed or expired JWT → returns None (optional auth never raises 401)."""
    from app.core.deps import get_optional_user

    from fastapi.security import HTTPAuthorizationCredentials

    mock_db = AsyncMock()
    request = MagicMock()
    request.cookies = {}
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.token")

    with patch(_MOCK_SETTINGS, _mock_settings()):
        with patch(_MOCK_JWT, side_effect=PyJWTError("expired")):
            result = await get_optional_user(
                request=request, credentials=creds, db=mock_db
            )
    assert result is None
    mock_db.scalar.assert_not_called()
