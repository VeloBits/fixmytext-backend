"""Tests for app/core/deps.py — the RS256/Keycloak-based auth dependency."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from main import app
from tests.conftest import make_mock_db, make_user

from app.db.session import get_db


def _make_client_with_db(mock_db):
    """Return TestClient with only get_db overridden (get_current_user uses real impl)."""

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app, raise_server_exceptions=False)


def test_get_current_user_no_credentials():
    """No Authorization header → 401."""
    mock_db = make_mock_db()
    client = _make_client_with_db(mock_db)
    resp = client.get("/api/v1/auth/me")
    app.dependency_overrides.clear()
    assert resp.status_code == 401


def test_get_current_user_invalid_token():
    """Invalid/malformed token → 401."""
    mock_db = make_mock_db()
    client = _make_client_with_db(mock_db)
    resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 401


def test_get_current_user_missing_bearer_prefix():
    """Token without Bearer prefix is rejected → 403 or 403."""
    mock_db = make_mock_db()
    client = _make_client_with_db(mock_db)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "some-token"})
    app.dependency_overrides.clear()
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_current_user_jit_provisions_new_user():
    """On first login with a valid Keycloak JWT, a new User row is JIT-provisioned."""
    from app.core.deps import get_current_user

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)  # user not found
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    keycloak_id = uuid.uuid4()
    fake_payload = {
        "sub": str(keycloak_id),
        "email": "newuser@example.com",
        "preferred_username": "newuser",
        "email_verified": True,
    }

    with patch(
        "app.core.deps.verify_jwt_raw", return_value=fake_payload
    ):
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake.jwt.token")
        user = await get_current_user(credentials=creds, db=mock_db)

    assert user.keycloak_id == keycloak_id
    assert user.email == "newuser@example.com"
    assert user.hashed_password is None
    assert user.is_email_verified is True
    mock_db.add.assert_called_once_with(user)
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_returns_existing_user():
    """Existing user (by keycloak_id) is returned without re-provisioning."""
    from app.core.deps import get_current_user

    keycloak_id = uuid.uuid4()
    existing_user = make_user(keycloak_id=keycloak_id)

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=existing_user)
    mock_db.add = MagicMock()

    fake_payload = {
        "sub": str(keycloak_id),
        "email": existing_user.email,
        "preferred_username": existing_user.display_name,
    }

    with patch("app.core.deps.verify_jwt_raw", return_value=fake_payload):
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake.jwt.token")
        user = await get_current_user(credentials=creds, db=mock_db)

    assert user is existing_user
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_current_user_inactive_user_raises_401():
    """Valid token but user is inactive → 401."""
    from fastapi import HTTPException

    from app.core.deps import get_current_user

    keycloak_id = uuid.uuid4()
    inactive_user = make_user(keycloak_id=keycloak_id, is_active=False)

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=inactive_user)

    fake_payload = {"sub": str(keycloak_id), "email": inactive_user.email}

    with patch("app.core.deps.verify_jwt_raw", return_value=fake_payload):
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake.jwt.token")
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=mock_db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_optional_user_no_credentials_returns_none():
    """No credentials → None (not authenticated)."""
    from app.core.deps import get_optional_user

    result = await get_optional_user(credentials=None, db=AsyncMock())
    assert result is None


@pytest.mark.asyncio
async def test_get_optional_user_invalid_token_returns_none():
    """Invalid token for optional auth → None (treated as anonymous)."""
    from fastapi.security import HTTPAuthorizationCredentials

    from app.core.deps import get_optional_user

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.token")

    from jwt.exceptions import PyJWTError

    with patch("app.core.deps.verify_jwt_raw", side_effect=PyJWTError("bad token")):
        result = await get_optional_user(credentials=creds, db=AsyncMock())

    assert result is None


def test_get_optional_user_no_auth_on_public_endpoint():
    """No token for optional-auth endpoint → anonymous access is accepted.

    Uses /api/v1/share/{id} which also uses get_optional_user and is still
    served by the monolith (text endpoints moved to text-svc in Sprint 4e).
    A non-existent share ID returns 404, which is acceptable — the important
    assertion is that a missing auth header does not produce a 401/403.
    """
    mock_db = make_mock_db()

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/share/nonexistent-id")
    app.dependency_overrides.clear()
    # 404 (share not found) is fine — what matters is we did NOT get 401/403
    assert resp.status_code not in (401, 403)
