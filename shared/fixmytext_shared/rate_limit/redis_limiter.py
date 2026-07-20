"""Redis-backed sliding-window rate limiter.

The limiter does **not** import a Redis client directly. Callers pass a
``redis_factory`` callable that returns the current Redis client (or
``None`` when Redis is unavailable). This keeps the shared package
agnostic of how each service manages its Redis connection lifecycle.

The check-and-increment is done in a single Lua script so it is atomic — two
concurrent requests can't both read an under-limit count and then both add
(the classic sorted-set race). When Redis is unavailable the limiter falls
back to an in-process limiter rather than degrading to *no* limit (M-4): a
Redis outage must never silently disable quotas.
"""

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request

from fixmytext_shared.rate_limit.memory import InMemoryRateLimiter

logger = logging.getLogger(__name__)

# Atomic sliding-window check: drop expired members, count, and only then add
# (if under the limit). Returns 1 when allowed, 0 when the limit is hit.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= max_requests then
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)
return 1
"""


class RedisRateLimiter:
    """Atomic sliding-window rate limiter backed by Redis sorted sets.

    Each key is a sorted set keyed by Unix-timestamp scores. The Lua script
    expires old members, counts, and conditionally adds — all atomically.
    When ``redis_factory()`` returns ``None`` (or a Redis call errors) the
    limiter delegates to an in-process :class:`InMemoryRateLimiter` so the
    quota still holds per-replica instead of failing open.
    """

    def __init__(
        self,
        redis_factory: Callable[[], Any | None],
        max_requests: int,
        window_seconds: int,
        prefix: str = "rl",
    ):
        self._redis_factory = redis_factory
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._prefix = prefix
        # Fail-closed fallback — never degrade to "no limit" when Redis is down.
        self._fallback = InMemoryRateLimiter(max_requests, window_seconds)

    async def check(self, request: Request, user_id: str | None = None) -> None:
        """Check rate limit. Raises HTTPException(429) if exceeded."""
        redis = self._redis_factory()
        if redis is None:
            # Redis unavailable — enforce per-process instead of failing open.
            await self._fallback.check(request, user_id=user_id)
            return

        if user_id:
            raw_key = f"user:{user_id}"
        else:
            raw_key = request.client.host if request.client else "unknown"

        key = f"{self._prefix}:{raw_key}"
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex}"  # unique so equal timestamps don't collide

        try:
            allowed = await redis.eval(
                _SLIDING_WINDOW_LUA,
                1,
                key,
                now,
                self.window_seconds,
                self.max_requests,
                member,
            )
        except Exception:
            # Transient Redis error — degrade to the in-process limiter, not open.
            logger.warning(
                "Redis rate-limit eval failed; using in-memory fallback", exc_info=True
            )
            await self._fallback.check(request, user_id=user_id)
            return

        if not allowed:
            logger.warning(
                "RATE LIMIT (Redis) hit for %s (max %d in %ds)",
                raw_key,
                self.max_requests,
                self.window_seconds,
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again shortly.",
                headers={"Retry-After": str(self.window_seconds)},
            )
