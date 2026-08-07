"""Rate limiters for account-svc - thin shim over fixmytext_shared.

Backed by the same Redis instance (``REDIS_URL``) as the other services so the
limit holds across replicas; falls back to in-memory when Redis is absent.
"""

from fixmytext_shared.rate_limit import create_limiter as _shared_create_limiter

from app.core.config import settings


def _get_redis():
    """Lazy Redis getter to avoid circular imports at module-load time."""
    from app.core.redis import get_redis as _gr

    return _gr()


# Verification-email resend: authenticated but email-amplification-abusable -
# each call makes Keycloak send a real email. Keyed per user, prefix
# ``rl:resend-verification``. (Signup itself is Keycloak-hosted and not proxied
# through this service, so there is no registration limiter here.)
resend_verification_limiter = _shared_create_limiter(
    max_requests=settings.RESEND_VERIFICATION_RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RESEND_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS,
    prefix="rl:resend-verification",
    redis_factory=_get_redis if settings.REDIS_URL else None,
)

__all__ = ["resend_verification_limiter"]
