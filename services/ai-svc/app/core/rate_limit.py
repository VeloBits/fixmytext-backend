"""Rate limiter for ai-svc - thin shim over fixmytext_shared.

Uses the same shared ``create_limiter`` factory as the monolith and shares
the same Redis instance (``REDIS_URL``). The rate-limit key prefix is
``rl:ai`` - identical to the monolith - so the quota is enforced
cross-service (same ``rl:ai:<user_id>`` key in Redis).
"""

from fixmytext_shared.rate_limit import create_limiter as _shared_create_limiter

from app.core.config import settings


def _get_redis():
    """Lazy Redis getter to avoid circular imports at module-load time."""
    from app.core.redis import get_redis as _gr

    return _gr()


ai_limiter = _shared_create_limiter(
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    prefix="rl:ai",
    redis_factory=_get_redis if settings.REDIS_URL else None,
)

__all__ = ["ai_limiter"]
