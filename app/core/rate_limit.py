"""
Rate limiting for API endpoints.

Uses Redis sorted-set sliding window when available, with automatic
fallback to an in-memory implementation for single-instance deployments.
"""

import logging
import time

from fastapi import HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Sliding-window rate limiter backed by an in-memory dict.

    Keys are either ``user:<user_id>`` (for authenticated requests) or the
    client IP address.  Expired timestamps are purged on every check.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ):
        self.max_requests = max_requests or settings.RATE_LIMIT_MAX_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        self._hits: dict[str, list[float]] = {}

    async def check(self, request: Request, user_id: str | None = None) -> None:
        """Check rate limit. Raises HTTPException(429) if exceeded."""
        if user_id:
            key = f"user:{user_id}"
        else:
            key = request.client.host if request.client else "unknown"

        now = time.time()

        # Prune expired timestamps for this key.
        if key in self._hits:
            self._hits[key] = [
                t for t in self._hits[key] if now - t < self.window_seconds
            ]
            # Remove truly empty keys to prevent unbounded memory growth.
            if not self._hits[key]:
                del self._hits[key]

        # Check whether the limit has been reached *before* recording the hit.
        current = self._hits.get(key, [])
        if len(current) >= self.max_requests:
            logger.warning(
                "RATE LIMIT hit for %s (%d/%d in %ds)",
                key,
                len(current),
                self.max_requests,
                self.window_seconds,
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again shortly.",
            )

        # Record the new hit.  Use explicit setdefault so we do not rely on
        # defaultdict creating a list behind the rate-check above.
        self._hits.setdefault(key, []).append(now)


class RedisRateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets.

    Each key is a sorted set where scores are Unix timestamps. On every
    check we remove expired members, count remaining ones, and add the
    current timestamp.  The key auto-expires after the window closes.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
        prefix: str = "rl",
    ):
        self.max_requests = max_requests or settings.RATE_LIMIT_MAX_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        self._prefix = prefix

    async def check(self, request: Request, user_id: str | None = None) -> None:
        """Check rate limit via Redis. Raises HTTPException(429) if exceeded."""
        from app.core.redis import get_redis

        redis = get_redis()
        if redis is None:
            return  # Redis unavailable — skip (caller should chain with in-memory)

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

        current_count = results[1]  # zcard result
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


def create_limiter(
    max_requests: int | None = None,
    window_seconds: int | None = None,
    prefix: str = "rl",
) -> RedisRateLimiter | InMemoryRateLimiter:
    """Create a rate limiter — prefers Redis when ``REDIS_URL`` is configured."""
    if settings.REDIS_URL:
        return RedisRateLimiter(max_requests, window_seconds, prefix)
    return InMemoryRateLimiter(max_requests, window_seconds)


# Default limiter instance used by AI endpoints
ai_limiter = create_limiter(prefix="rl:ai")

# Stricter limiter for authentication endpoints (brute-force protection)
auth_limiter = create_limiter(max_requests=10, window_seconds=60, prefix="rl:auth")

# Very strict limiter for password reset initiation — costlier per request
# (DB write + email) and a common abuse vector for user enumeration and spam.
forgot_password_limiter = create_limiter(
    max_requests=3, window_seconds=60, prefix="rl:forgot-pw"
)
