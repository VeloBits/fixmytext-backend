"""Unit tests for core helpers: Redis lifecycle, optional JWT auth, rate limit.

Redis is never contacted for real — the client class is replaced with mocks so
the connect / ping-failure / close paths run deterministically. Auth tests call
``get_optional_user`` directly with a patched ``verify_jwt_raw``.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

from app.core import auth as auth_module
from app.core import redis as redis_core
from app.core.auth import get_optional_user
from app.core.rate_limit import _get_redis as rate_limit_get_redis

# ── Redis lifecycle ───────────────────────────────────────────────────────


async def test_init_redis_without_url_disables_redis(monkeypatch):
    monkeypatch.setattr(redis_core, "_pool", None)
    with patch.object(redis_core, "settings", SimpleNamespace(REDIS_URL="")):
        await redis_core.init_redis()
    assert redis_core.get_redis() is None


async def test_init_redis_success_then_close(monkeypatch):
    monkeypatch.setattr(redis_core, "_pool", None)
    fake = MagicMock()
    fake.ping = AsyncMock()
    fake.aclose = AsyncMock()
    mock_cls = MagicMock()
    mock_cls.from_url.return_value = fake
    with (
        patch.object(
            redis_core, "settings", SimpleNamespace(REDIS_URL="redis://test:6379/0")
        ),
        patch.object(redis_core, "Redis", mock_cls),
    ):
        await redis_core.init_redis()
        assert redis_core.get_redis() is fake
        fake.ping.assert_awaited_once()
        await redis_core.close_redis()
    fake.aclose.assert_awaited_once()
    assert redis_core.get_redis() is None


async def test_init_redis_connection_failure_falls_back(monkeypatch):
    monkeypatch.setattr(redis_core, "_pool", None)
    fake = MagicMock()
    fake.ping = AsyncMock(side_effect=ConnectionError("refused"))
    mock_cls = MagicMock()
    mock_cls.from_url.return_value = fake
    with (
        patch.object(
            redis_core, "settings", SimpleNamespace(REDIS_URL="redis://down:6379/0")
        ),
        patch.object(redis_core, "Redis", mock_cls),
    ):
        await redis_core.init_redis()
    assert redis_core.get_redis() is None


async def test_close_redis_is_noop_when_not_connected(monkeypatch):
    monkeypatch.setattr(redis_core, "_pool", None)
    await redis_core.close_redis()
    assert redis_core.get_redis() is None


def test_rate_limit_lazy_redis_getter(monkeypatch):
    monkeypatch.setattr(redis_core, "_pool", None)
    assert rate_limit_get_redis() is None


# ── Optional JWT auth ─────────────────────────────────────────────────────


def _auth_settings():
    return SimpleNamespace(
        KEYCLOAK_JWKS_URL="http://keycloak/jwks",
        KEYCLOAK_AUDIENCE=None,
        KEYCLOAK_ISSUER=None,
    )


def _creds(token: str = "some.jwt.token"):
    return SimpleNamespace(credentials=token)


async def test_get_optional_user_without_credentials_is_visitor():
    assert await get_optional_user(None) is None


async def test_get_optional_user_jwks_unreachable_is_visitor():
    with (
        patch.object(auth_module, "settings", _auth_settings()),
        patch.object(
            auth_module,
            "verify_jwt_raw",
            AsyncMock(side_effect=PyJWKClientConnectionError("jwks down")),
        ),
    ):
        assert await get_optional_user(_creds()) is None


async def test_get_optional_user_invalid_token_is_visitor():
    with (
        patch.object(auth_module, "settings", _auth_settings()),
        patch.object(
            auth_module,
            "verify_jwt_raw",
            AsyncMock(side_effect=PyJWTError("bad signature")),
        ),
    ):
        assert await get_optional_user(_creds()) is None


async def test_get_optional_user_missing_sub_is_visitor():
    with (
        patch.object(auth_module, "settings", _auth_settings()),
        patch.object(
            auth_module,
            "verify_jwt_raw",
            AsyncMock(return_value={"email": "nosub@example.com"}),
        ),
    ):
        assert await get_optional_user(_creds()) is None


async def test_get_optional_user_valid_token_builds_user():
    payload = {
        "sub": "22222222-2222-2222-2222-222222222222",
        "email": "user@example.com",
        "email_verified": True,
    }
    with (
        patch.object(auth_module, "settings", _auth_settings()),
        patch.object(auth_module, "verify_jwt_raw", AsyncMock(return_value=payload)),
    ):
        user = await get_optional_user(_creds())
    assert user is not None
    assert user.id == payload["sub"]
    assert user.email == "user@example.com"
    assert user.is_email_verified is True
