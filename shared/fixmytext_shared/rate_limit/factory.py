"""Factory that picks a Redis limiter when a redis_factory is supplied, else in-memory."""

from collections.abc import Callable
from typing import Any

from fixmytext_shared.rate_limit.memory import InMemoryRateLimiter
from fixmytext_shared.rate_limit.redis_limiter import RedisRateLimiter


def create_limiter(
    *,
    max_requests: int,
    window_seconds: int,
    prefix: str = "rl",
    redis_factory: Callable[[], Any | None] | None = None,
) -> RedisRateLimiter | InMemoryRateLimiter:
    """Create a rate limiter.

    When ``redis_factory`` is provided, returns a ``RedisRateLimiter`` that
    will call it on each check. Otherwise returns ``InMemoryRateLimiter``.
    """
    if redis_factory is not None:
        return RedisRateLimiter(redis_factory, max_requests, window_seconds, prefix)
    return InMemoryRateLimiter(max_requests, window_seconds)
