"""Rate limiter for text-svc — thin shim over fixmytext_shared.

Mirrors ai-svc: the same shared ``create_limiter`` factory backed by the same
Redis instance (``REDIS_URL``), with key prefix ``rl:text`` so the limit holds
across replicas. Falls back to an in-memory limiter when Redis is not configured.
"""

from fixmytext_shared.rate_limit import create_limiter as _shared_create_limiter

from app.core.config import settings


def _get_redis():
    """Lazy Redis getter to avoid circular imports at module-load time."""
    from app.core.redis import get_redis as _gr

    return _gr()


text_limiter = _shared_create_limiter(
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    prefix="rl:text",
    redis_factory=_get_redis if settings.REDIS_URL else None,
)

__all__ = ["text_limiter"]
