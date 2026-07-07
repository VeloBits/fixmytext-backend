"""Tests for rate limiters (in-memory + Redis with mocked client)."""

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
    def _fake_redis(self, current_count: int):
        """Build a mock that mimics aioredis pipeline behaviour."""
        pipe = MagicMock()
        pipe.zremrangebyscore = MagicMock()
        pipe.zcard = MagicMock()
        pipe.zadd = MagicMock()
        pipe.expire = MagicMock()
        # results[1] is zcard's value
        pipe.execute = AsyncMock(return_value=[None, current_count, None, None])
        client = MagicMock()
        client.pipeline = MagicMock(return_value=pipe)
        return client

    async def test_passes_when_under_limit(self, request_factory):
        client = self._fake_redis(current_count=0)
        limiter = RedisRateLimiter(
            redis_factory=lambda: client,
            max_requests=5,
            window_seconds=60,
        )
        await limiter.check(request_factory("1.2.3.4"))

    async def test_raises_429_when_over_limit(self, request_factory):
        client = self._fake_redis(current_count=10)
        limiter = RedisRateLimiter(
            redis_factory=lambda: client,
            max_requests=5,
            window_seconds=60,
        )
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check(request_factory("1.2.3.4"))
        assert exc_info.value.status_code == 429

    async def test_no_op_when_redis_unavailable(self, request_factory):
        limiter = RedisRateLimiter(
            redis_factory=lambda: None,
            max_requests=1,
            window_seconds=60,
        )
        # should not raise even when called many times
        for _ in range(5):
            await limiter.check(request_factory("1.2.3.4"))


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
