"""M-8: /auth/register is throttled per client IP.

Exercises the limiter directly (in-memory fallback, no Redis configured in
tests) so the cap is enforced without standing up Keycloak.
"""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.config import settings
from app.core.rate_limit import register_limiter


def _req(ip: str = "203.0.113.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/register",
            "headers": [],
            "client": (ip, 0),
            "query_string": b"",
        }
    )


async def test_register_limiter_blocks_after_cap():
    cap = settings.REGISTER_RATE_LIMIT_MAX_REQUESTS
    key = "ip:register-test-unique"  # isolated bucket for this test
    request = _req()

    # First `cap` requests are allowed.
    for _ in range(cap):
        await register_limiter.check(request, user_id=key)

    # The next one is rejected with 429.
    with pytest.raises(HTTPException) as exc:
        await register_limiter.check(request, user_id=key)
    assert exc.value.status_code == 429


async def test_register_limiter_isolates_per_key():
    """A different IP key has its own quota."""
    await register_limiter.check(_req(), user_id="ip:register-other-key")
