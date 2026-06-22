"""Optional Redis connection pool + session revocation helpers.

When ``REDIS_URL`` is not set the module gracefully returns ``None`` and
callers fall back to in-memory alternatives. Session revocation degrades
gracefully too: if Redis is unavailable, revocations are not persisted
(stolen cookies remain valid until they expire naturally).
"""

import logging
import time

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: Redis | None = None

_SESSION_REVOKE_PREFIX = "sess:revoked:"


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
        # Log only host:port — URL may contain credentials in redis://:pass@host form.
        safe_url = settings.REDIS_URL.split("@")[-1] if "@" in settings.REDIS_URL else settings.REDIS_URL
        logger.info("Redis connected: %s", safe_url)
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


async def revoke_session(sub: str, ttl_seconds: int) -> None:
    """Mark all sessions for *sub* issued before now as revoked.

    Stores ``int(time.time()) + 1`` so that ``is_session_revoked`` (which uses
    strict ``<``) correctly blocks cookies whose ``iat`` equals the current
    second.  A new session issued in the next second or later will have
    ``iat >= revoked_at`` and will not be blocked.
    """
    redis = get_redis()
    if redis is None:
        logger.warning("revoke_session: Redis unavailable — revocation not persisted for sub=%s", sub)
        return
    await redis.set(
        f"{_SESSION_REVOKE_PREFIX}{sub}",
        int(time.time()) + 1,
        ex=max(1, ttl_seconds),
    )


async def is_session_revoked(sub: str, iat: int) -> bool:
    """Return True if the session cookie was issued before the last logout.

    If Redis is unavailable, returns False (fail-open) to avoid blocking all
    cookie-auth requests during a Redis outage.
    """
    redis = get_redis()
    if redis is None:
        return False
    revoked_at = await redis.get(f"{_SESSION_REVOKE_PREFIX}{sub}")
    if revoked_at is None:
        return False
    return iat < int(revoked_at)
