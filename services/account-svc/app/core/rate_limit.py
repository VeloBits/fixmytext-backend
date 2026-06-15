"""Rate limiters for account-svc — thin shim over fixmytext_shared.

Backed by the same Redis instance (``REDIS_URL``) as the other services so the
limit holds across replicas; falls back to in-memory when Redis is absent.
"""

from fixmytext_shared.rate_limit import create_limiter as _shared_create_limiter

from app.core.config import settings


def _get_redis():
    """Lazy Redis getter to avoid circular imports at module-load time."""
    from app.core.redis import get_redis as _gr

    return _gr()


# Registration: sensitive, abusable (mass account creation, verification-email
# amplification, address enumeration). Keyed per client IP, prefix ``rl:register``.
register_limiter = _shared_create_limiter(
    max_requests=settings.REGISTER_RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.REGISTER_RATE_LIMIT_WINDOW_SECONDS,
    prefix="rl:register",
    redis_factory=_get_redis if settings.REDIS_URL else None,
)

__all__ = ["register_limiter"]
