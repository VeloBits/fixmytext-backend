"""Redis-backed sliding-window rate limiter.

The limiter does **not** import a Redis client directly. Callers pass a
``redis_factory`` callable that returns the current Redis client (or
``None`` when Redis is unavailable). This keeps the shared package
agnostic of how each service manages its Redis connection lifecycle.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets.

    Each key is a sorted set where scores are Unix timestamps. On every
    check we remove expired members, count remaining ones, and add the
    current timestamp. The key auto-expires after the window closes.

    When ``redis_factory()`` returns ``None`` the check is a no-op
    (graceful degradation — caller may chain with InMemoryRateLimiter).
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

    async def check(self, request: Request, user_id: str | None = None) -> None:
        """Check rate limit via Redis. Raises HTTPException(429) if exceeded."""
        redis = self._redis_factory()
        if redis is None:
            return  # Redis unavailable — degrade open

        if user_id:
            raw_key = f"user:{user_id}"
        else:
            raw_key = request.client.host if request.client else "unknown"

        key = f"{self._prefix}:{raw_key}"
        now = time.time()
        window_start = now - self.window_seconds

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, self.window_seconds + 1)
        results = await pipe.execute()

        current_count = results[1]
        if current_count >= self.max_requests:
            logger.warning(
                "RATE LIMIT (Redis) hit for %s (%d/%d in %ds)",
                raw_key,
                current_count,
                self.max_requests,
                self.window_seconds,
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again shortly.",
            )
