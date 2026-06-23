"""Tests for get_optional_user JIT provisioning (B1 fix).

Verifies that a brand-new Keycloak user who hits a share endpoint with a
valid Bearer JWT gets JIT-provisioned so their share is linked to their
account — not created anonymously.

Prior to the B1 fix, get_optional_user discarded jwt_payload and never
called jit_provision_user, so any user whose first request was POST /share
ended up with user=None (anonymous share).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MOCK_JWT = "app.core.deps.verify_jwt_raw"


def _valid_payload(kc_id: uuid.UUID) -> dict:
    return {
        "sub": str(kc_id),
        "email": "newuser@example.com",
        "email_verified": True,
        "preferred_username": "newuser",
    }


def _make_user(kc_id: uuid.UUID) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.keycloak_id = kc_id
    u.email = "newuser@example.com"
    u.display_name = "New User"
    u.is_active = True
    u.is_email_verified = True
    return u


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optional_user_jit_provisions_new_bearer_user():
    """A new KC user with a valid Bearer JWT is JIT-provisioned by get_optional_user.

    Before B1 fix: user=None (anonymous).
    After B1 fix: user is provisioned and returned.
    """
    from app.core.deps import get_optional_user
    from app.db.models.user import User
    from fastapi.security import HTTPAuthorizationCredentials

    kc_id = uuid.uuid4()
    provisioned_user = _make_user(kc_id)
    payload = _valid_payload(kc_id)

    mock_db = AsyncMock()
    # First scalar() returns None (user not in DB yet); JIT adds the user.
    mock_db.scalar = AsyncMock(return_value=None)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    mock_request = MagicMock()
    mock_request.cookies.get = MagicMock(return_value=None)

    mock_creds = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="valid.jwt.token"
    )

    with patch(_MOCK_JWT, return_value=payload):
        with patch(
            "app.core.deps.jit_provision_user", return_value=provisioned_user
        ) as mock_jit:
            result = await get_optional_user(mock_request, mock_creds, mock_db)

    assert result is provisioned_user
    mock_jit.assert_called_once()
    call_kwargs = mock_jit.call_args
    assert call_kwargs[0][2] == kc_id  # keycloak_id arg


@pytest.mark.asyncio
async def test_optional_user_cookie_only_no_provision():
    """Cookie-only auth cannot JIT-provision: no jwt_payload → returns None for unknown user."""
    import os

    from app.core.deps import get_optional_user
    from app.core.session_cookie import build_claims, sign_session

    kc_id = uuid.uuid4()
    secret = os.environ.get("SECRET_KEY", "test-secret-key-at-least-32-characters")
    claims = build_claims(
        sub=str(kc_id),
        email="cookie@example.com",
        email_verified=True,
        roles=[],
        max_age_seconds=3600,
    )
    cookie_val = sign_session(claims, secret)

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)  # unknown user, no DB row

    mock_request = MagicMock()
    mock_request.cookies.get = MagicMock(return_value=cookie_val)

    with patch("app.core.deps.settings") as mock_settings:
        mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
        mock_settings.SESSION_COOKIE_SECRET = secret
        mock_settings.KEYCLOAK_JWKS_URL = "http://keycloak/jwks"
        mock_settings.KEYCLOAK_AUDIENCE = None
        mock_settings.KEYCLOAK_ISSUER = None

        with patch("app.core.deps.jit_provision_user") as mock_jit:
            result = await get_optional_user(mock_request, None, mock_db)

    assert result is None
    mock_jit.assert_not_called()


@pytest.mark.asyncio
async def test_optional_user_returns_existing_user():
    """Existing user with valid Bearer JWT is returned without calling jit_provision_user."""
    from app.core.deps import get_optional_user
    from fastapi.security import HTTPAuthorizationCredentials

    kc_id = uuid.uuid4()
    existing_user = _make_user(kc_id)
    payload = _valid_payload(kc_id)

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=existing_user)

    mock_request = MagicMock()
    mock_request.cookies.get = MagicMock(return_value=None)

    mock_creds = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="valid.jwt.token"
    )

    with patch(_MOCK_JWT, return_value=payload):
        with patch("app.core.deps.jit_provision_user") as mock_jit:
            result = await get_optional_user(mock_request, mock_creds, mock_db)

    assert result is existing_user
    mock_jit.assert_not_called()


@pytest.mark.asyncio
async def test_optional_user_inactive_user_returns_none():
    """An inactive user returns None even if their JWT is valid."""
    from app.core.deps import get_optional_user
    from fastapi.security import HTTPAuthorizationCredentials

    kc_id = uuid.uuid4()
    inactive_user = _make_user(kc_id)
    inactive_user.is_active = False

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=inactive_user)

    mock_request = MagicMock()
    mock_request.cookies.get = MagicMock(return_value=None)

    mock_creds = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="valid.jwt.token"
    )

    with patch(_MOCK_JWT, return_value=_valid_payload(kc_id)):
        result = await get_optional_user(mock_request, mock_creds, mock_db)

    assert result is None


@pytest.mark.asyncio
async def test_optional_user_no_credentials_returns_none():
    """No Bearer token and no cookie → None without touching the DB."""
    from app.core.deps import get_optional_user

    mock_db = AsyncMock()
    mock_request = MagicMock()
    mock_request.cookies.get = MagicMock(return_value=None)

    result = await get_optional_user(mock_request, None, mock_db)

    assert result is None
    mock_db.scalar.assert_not_called()
