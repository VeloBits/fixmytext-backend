"""Unit tests for app.core.redis and the app.core.rate_limit shim.

The redis client is fully mocked — no real Redis connection is made.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import rate_limit
from app.core import redis as redis_module
from app.core.config import settings

# ── init_redis ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_redis_disabled_without_url(monkeypatch):
    """REDIS_URL unset → init is a no-op and get_redis() stays None."""
    monkeypatch.setattr(redis_module, "_pool", None)
    monkeypatch.setattr(settings, "REDIS_URL", "")

    await redis_module.init_redis()
    assert redis_module.get_redis() is None


@pytest.mark.asyncio
async def test_init_redis_success(monkeypatch):
    """REDIS_URL set and ping succeeds → pool is stored."""
    fake_pool = AsyncMock()
    fake_redis_cls = MagicMock()
    fake_redis_cls.from_url = MagicMock(return_value=fake_pool)

    monkeypatch.setattr(redis_module, "_pool", None)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(redis_module, "Redis", fake_redis_cls)

    await redis_module.init_redis()
    fake_pool.ping.assert_awaited_once()
    assert redis_module.get_redis() is fake_pool


@pytest.mark.asyncio
async def test_init_redis_falls_back_on_connection_error(monkeypatch):
    """Ping failure → pool stays None (in-memory fallback)."""
    fake_pool = AsyncMock()
    fake_pool.ping = AsyncMock(side_effect=ConnectionError("refused"))
    fake_redis_cls = MagicMock()
    fake_redis_cls.from_url = MagicMock(return_value=fake_pool)

    monkeypatch.setattr(redis_module, "_pool", None)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(redis_module, "Redis", fake_redis_cls)

    await redis_module.init_redis()
    assert redis_module.get_redis() is None


# ── close_redis ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_redis_closes_pool(monkeypatch):
    fake_pool = AsyncMock()
    monkeypatch.setattr(redis_module, "_pool", fake_pool)

    await redis_module.close_redis()
    fake_pool.aclose.assert_awaited_once()
    assert redis_module.get_redis() is None


@pytest.mark.asyncio
async def test_close_redis_noop_when_uninitialised(monkeypatch):
    monkeypatch.setattr(redis_module, "_pool", None)
    await redis_module.close_redis()
    assert redis_module.get_redis() is None


# ── rate_limit shim ───────────────────────────────────────────────────────────


def test_rate_limit_get_redis_delegates_to_core(monkeypatch):
    """The lazy redis getter returns whatever app.core.redis holds."""
    sentinel = MagicMock()
    monkeypatch.setattr(redis_module, "_pool", sentinel)
    assert rate_limit._get_redis() is sentinel

    monkeypatch.setattr(redis_module, "_pool", None)
    assert rate_limit._get_redis() is None


def test_ai_limiter_configured_from_settings():
    assert rate_limit.ai_limiter is not None
    assert rate_limit.ai_limiter.max_requests == settings.RATE_LIMIT_MAX_REQUESTS
    assert rate_limit.ai_limiter.window_seconds == settings.RATE_LIMIT_WINDOW_SECONDS
