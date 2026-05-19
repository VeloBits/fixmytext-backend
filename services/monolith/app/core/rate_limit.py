"""Rate limiters — thin shim over fixmytext_shared.

The classes themselves live in ``fixmytext_shared.rate_limit``. The
module-level singletons (`ai_limiter`, `auth_limiter`, etc.) are recreated
here so existing call sites that do ``from app.core.rate_limit import
ai_limiter`` keep working unchanged.

The shared classes don't import the Redis getter — we inject it via a
``redis_factory`` callable so the shared package stays agnostic of how
each service manages its Redis lifecycle.
"""

from app.core.config import settings
from app.core.redis import get_redis
from fixmytext_shared.rate_limit import (
    InMemoryRateLimiter as _SharedInMemoryRateLimiter,
)
from fixmytext_shared.rate_limit import (
    RedisRateLimiter as _SharedRedisRateLimiter,
)
from fixmytext_shared.rate_limit import (
    create_limiter as _shared_create_limiter,
)


class InMemoryRateLimiter(_SharedInMemoryRateLimiter):
    """Monolith-bound limiter: defaults to settings when args are omitted.

    Preserves the pre-extraction call shape ``InMemoryRateLimiter()`` so
    existing imports and tests keep working without changes.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ):
        super().__init__(
            max_requests=max_requests or settings.RATE_LIMIT_MAX_REQUESTS,
            window_seconds=window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS,
        )


class RedisRateLimiter(_SharedRedisRateLimiter):
    """Monolith-bound Redis limiter: defaults to settings + monolith ``get_redis``."""

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
        prefix: str = "rl",
    ):
        super().__init__(
            redis_factory=get_redis,
            max_requests=max_requests or settings.RATE_LIMIT_MAX_REQUESTS,
            window_seconds=window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS,
            prefix=prefix,
        )


def create_limiter(
    max_requests: int | None = None,
    window_seconds: int | None = None,
    prefix: str = "rl",
) -> RedisRateLimiter | InMemoryRateLimiter:
    """Create a limiter — prefers Redis when ``REDIS_URL`` is configured.

    Wraps the shared factory with the monolith's settings + Redis getter so
    legacy call sites (``create_limiter(prefix="rl:ai")``) keep working.
    """
    base = _shared_create_limiter(
        max_requests=max_requests or settings.RATE_LIMIT_MAX_REQUESTS,
        window_seconds=window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS,
        prefix=prefix,
        redis_factory=get_redis if settings.REDIS_URL else None,
    )
    return base  # type: ignore[return-value]


# Default limiter instance used by AI endpoints
ai_limiter = create_limiter(prefix="rl:ai")

# Stricter limiter for authentication endpoints (brute-force protection)
auth_limiter = create_limiter(max_requests=10, window_seconds=60, prefix="rl:auth")

# Very strict limiter for password reset initiation — costlier per request
# (DB write + email) and a common abuse vector for user enumeration and spam.
forgot_password_limiter = create_limiter(
    max_requests=3, window_seconds=60, prefix="rl:forgot-pw"
)

# Per-user cooldown for /auth/resend-verification. Keyed by user_id (not IP),
# so a single user can't request more than one verification email every two
# minutes regardless of which client they hit the API from.
verification_resend_limiter = create_limiter(
    max_requests=1, window_seconds=120, prefix="rl:verify-resend"
)


__all__ = [
    "InMemoryRateLimiter",
    "RedisRateLimiter",
    "ai_limiter",
    "auth_limiter",
    "create_limiter",
    "forgot_password_limiter",
    "verification_resend_limiter",
]
