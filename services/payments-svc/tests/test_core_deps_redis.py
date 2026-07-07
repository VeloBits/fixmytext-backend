"""Unit tests for app.core.deps.get_current_user and app.core.redis.

get_current_user: JWT verification, JIT provisioning, and the inactive-user
guard, all with a mocked session and patched shared-auth helpers. Redis:
the optional pool lifecycle (disabled, connected, connection failure).

The internal-secret guard is covered in test_internal_auth.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import redis as redis_mod
from app.core.config import settings
from app.core.deps import get_current_user

# ── Helpers ───────────────────────────────────────────────────────────────────


def _creds(token: str = "some.jwt.token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _user_row(keycloak_id: uuid.UUID, active: bool = True) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.keycloak_id = keycloak_id
    u.is_active = active
    return u


# ── get_current_user ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_user_no_credentials_returns_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=None, db=AsyncMock())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_get_current_user_invalid_token_returns_401():
    with (
        patch(
            "app.core.deps.verify_jwt_raw",
            new_callable=AsyncMock,
            side_effect=Exception("expired"),
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await get_current_user(credentials=_creds(), db=AsyncMock())
    assert exc.value.status_code == 401
    assert "expired or invalid" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_non_uuid_subject_returns_401():
    with (
        patch(
            "app.core.deps.verify_jwt_raw",
            new_callable=AsyncMock,
            return_value={"sub": "not-a-uuid"},
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await get_current_user(credentials=_creds(), db=AsyncMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_returns_existing_active_user():
    keycloak_id = uuid.uuid4()
    user = _user_row(keycloak_id)
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=user)

    with patch(
        "app.core.deps.verify_jwt_raw",
        new_callable=AsyncMock,
        return_value={"sub": str(keycloak_id)},
    ):
        result = await get_current_user(credentials=_creds(), db=db)
    assert result is user


@pytest.mark.asyncio
async def test_get_current_user_inactive_user_returns_401():
    keycloak_id = uuid.uuid4()
    user = _user_row(keycloak_id, active=False)
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=user)

    with (
        patch(
            "app.core.deps.verify_jwt_raw",
            new_callable=AsyncMock,
            return_value={"sub": str(keycloak_id)},
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await get_current_user(credentials=_creds(), db=db)
    assert exc.value.status_code == 401
    assert "inactive" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_jit_provisions_unknown_subject():
    keycloak_id = uuid.uuid4()
    payload = {"sub": str(keycloak_id), "email": "new@example.com"}
    provisioned = _user_row(keycloak_id)
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)  # no existing row

    with (
        patch(
            "app.core.deps.verify_jwt_raw",
            new_callable=AsyncMock,
            return_value=payload,
        ),
        patch(
            "app.core.deps.jit_provision_user",
            new_callable=AsyncMock,
            return_value=provisioned,
        ) as mock_jit,
    ):
        result = await get_current_user(credentials=_creds(), db=db)
    assert result is provisioned
    mock_jit.assert_awaited_once()
    assert mock_jit.await_args.args[2] == keycloak_id
    assert mock_jit.await_args.args[3] == payload


# ── Redis pool lifecycle ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_redis_disabled_without_url(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(redis_mod, "_pool", None)
    await redis_mod.init_redis()
    assert redis_mod.get_redis() is None


@pytest.mark.asyncio
async def test_init_redis_connects_and_close_clears_pool(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(redis_mod, "_pool", None)

    fake_pool = AsyncMock()
    with patch("app.core.redis.Redis") as mock_redis_cls:
        mock_redis_cls.from_url.return_value = fake_pool
        await redis_mod.init_redis()

    assert redis_mod.get_redis() is fake_pool
    fake_pool.ping.assert_awaited_once()

    await redis_mod.close_redis()
    fake_pool.aclose.assert_awaited_once()
    assert redis_mod.get_redis() is None


@pytest.mark.asyncio
async def test_init_redis_falls_back_to_none_on_connection_failure(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(redis_mod, "_pool", None)

    fake_pool = AsyncMock()
    fake_pool.ping = AsyncMock(side_effect=ConnectionError("refused"))
    with patch("app.core.redis.Redis") as mock_redis_cls:
        mock_redis_cls.from_url.return_value = fake_pool
        await redis_mod.init_redis()  # must not raise

    assert redis_mod.get_redis() is None


@pytest.mark.asyncio
async def test_close_redis_noop_when_pool_absent(monkeypatch):
    monkeypatch.setattr(redis_mod, "_pool", None)
    await redis_mod.close_redis()  # must not raise
    assert redis_mod.get_redis() is None
