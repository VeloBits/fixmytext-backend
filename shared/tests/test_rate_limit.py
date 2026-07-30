"""Tests for rate limiters (in-memory + Redis with mocked client)."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from fixmytext_shared.rate_limit import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    create_limiter,
)


@pytest.mark.asyncio
class TestInMemoryRateLimiter:
    async def test_allows_under_limit(self, request_factory):
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        req = request_factory("1.1.1.1")
        for _ in range(3):
            await limiter.check(req)

    async def test_blocks_over_limit(self, request_factory):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        req = request_factory("2.2.2.2")
        await limiter.check(req)
        await limiter.check(req)
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check(req)
        assert exc_info.value.status_code == 429

    async def test_separate_keys_for_different_ips(self, request_factory):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        await limiter.check(request_factory("3.3.3.3"))
        await limiter.check(request_factory("4.4.4.4"))

    async def test_user_id_overrides_ip(self, request_factory):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        req = request_factory("5.5.5.5")
        await limiter.check(req, user_id="alice")
        # different user, same IP -> separate bucket
        await limiter.check(req, user_id="bob")
        with pytest.raises(HTTPException):
            await limiter.check(req, user_id="alice")


@pytest.mark.asyncio
class TestRedisRateLimiter:
    def _fake_redis(self, *, allowed: bool):
        """Mock the atomic Lua eval: returns 1 (allowed) or 0 (over limit)."""
        client = MagicMock()
        client.eval = AsyncMock(return_value=1 if allowed else 0)
        return client

    async def test_passes_when_under_limit(self, request_factory):
        client = self._fake_redis(allowed=True)
        limiter = RedisRateLimiter(
            redis_factory=lambda: client,
            max_requests=5,
            window_seconds=60,
        )
        await limiter.check(request_factory("1.2.3.4"))

    async def test_raises_429_when_over_limit(self, request_factory):
        client = self._fake_redis(allowed=False)
        limiter = RedisRateLimiter(
            redis_factory=lambda: client,
            max_requests=5,
            window_seconds=60,
        )
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check(request_factory("1.2.3.4"))
        assert exc_info.value.status_code == 429

    async def test_fails_closed_via_in_memory_when_redis_unavailable(
        self, request_factory
    ):
        """M-4: Redis down must NOT mean 'no limit' - the in-process fallback
        still enforces the cap (here max_requests=1)."""
        limiter = RedisRateLimiter(
            redis_factory=lambda: None,
            max_requests=1,
            window_seconds=60,
        )
        req = request_factory("1.2.3.4")
        await limiter.check(req)  # 1st allowed
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check(req)  # 2nd over the in-memory cap
        assert exc_info.value.status_code == 429

    async def test_falls_back_to_in_memory_on_redis_error(self, request_factory):
        """A transient Redis error degrades to the in-process limiter, not open."""
        client = MagicMock()
        client.eval = AsyncMock(side_effect=ConnectionError("redis down"))
        limiter = RedisRateLimiter(
            redis_factory=lambda: client,
            max_requests=1,
            window_seconds=60,
        )
        req = request_factory("9.9.9.9")
        await limiter.check(req)  # 1st allowed (fallback)
        with pytest.raises(HTTPException):
            await limiter.check(req)  # 2nd blocked (fallback enforces)


@pytest.mark.asyncio
class TestRedisRateLimiterKeys:
    def _recording_redis(self):
        client = MagicMock()
        client.eval = AsyncMock(return_value=1)
        return client

    async def test_user_id_key_uses_prefix_and_user_bucket(self, request_factory):
        client = self._recording_redis()
        limiter = RedisRateLimiter(
            redis_factory=lambda: client,
            max_requests=5,
            window_seconds=60,
            prefix="myrl",
        )
        await limiter.check(request_factory("1.2.3.4"), user_id="alice")
        key = client.eval.await_args.args[2]
        assert key == "myrl:user:alice"

    async def test_missing_client_falls_back_to_unknown_key(self):
        client = self._recording_redis()
        request = MagicMock()
        request.client = None
        limiter = RedisRateLimiter(
            redis_factory=lambda: client,
            max_requests=5,
            window_seconds=60,
        )
        await limiter.check(request)
        assert client.eval.await_args.args[2] == "rl:unknown"


@pytest.mark.asyncio
class TestInMemoryRateLimiterExpiry:
    async def test_expired_hits_are_purged(self, request_factory):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        req = request_factory("8.8.8.8")
        await limiter.check(req)
        # Age the recorded hit past the window; the next check purges the key
        # entirely and the request is allowed again.
        limiter._hits["8.8.8.8"] = [time.time() - 120]
        await limiter.check(req)
        assert len(limiter._hits["8.8.8.8"]) == 1


class TestCreateLimiter:
    def test_returns_in_memory_when_no_redis_factory(self):
        limiter = create_limiter(max_requests=5, window_seconds=60)
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_returns_redis_when_factory_provided(self):
        limiter = create_limiter(
            max_requests=5,
            window_seconds=60,
            redis_factory=lambda: MagicMock(),
        )
        assert isinstance(limiter, RedisRateLimiter)
