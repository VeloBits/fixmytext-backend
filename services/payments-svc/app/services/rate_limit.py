"""Simple Redis-backed fixed-window rate limiter.

Used by order-creation endpoints to prevent API-key abuse and Razorpay call
exhaustion. Degrades gracefully to allow-all when Redis is unavailable.
"""

import logging

from fastapi import HTTPException

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


async def check_rate_limit(
    key: str,
    max_count: int,
    window_secs: int = 60,
) -> None:
    """Raise HTTP 429 if *key* has exceeded *max_count* calls in *window_secs*.

    Uses Redis INCR + EXPIRE (fixed window). Falls back to allow-all when Redis
    is unavailable so a Redis outage never blocks legitimate payments.
    """
    redis = get_redis()
    if redis is None:
        return
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_secs)
        if count > max_count:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait before trying again.",
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning("Rate limit check failed for key=%s — allowing request", key)
