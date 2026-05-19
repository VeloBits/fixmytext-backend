"""Optional Redis connection pool for distributed rate limiting and caching.

When ``REDIS_URL`` is not set the module gracefully returns ``None`` and
callers fall back to in-memory alternatives.
"""

import logging

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: Redis | None = None


async def init_redis() -> None:
    """Open the Redis connection pool (called from FastAPI lifespan)."""
    global _pool  # noqa: PLW0603
    if not settings.REDIS_URL:
        logger.info("REDIS_URL not set — Redis features disabled")
        return
    try:
        _pool = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await _pool.ping()
        logger.info("Redis connected: %s", settings.REDIS_URL)
    except Exception:
        logger.warning(
            "Redis connection failed — falling back to in-memory", exc_info=True
        )
        _pool = None


async def close_redis() -> None:
    """Close the Redis connection pool (called from FastAPI lifespan)."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def get_redis() -> Redis | None:
    """Return the Redis client or ``None`` if unavailable."""
    return _pool
