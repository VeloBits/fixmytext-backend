"""Client for the payments-svc entitlement gate (ai-svc).

Calls ``POST /internal/v1/check-access`` after the rate-limit check and before
invoking the model. ai-svc requests are always authenticated and every AI tool
is billable, so a gate outage fails CLOSED (503) — there is no free fallback
(the M-4 lesson: a silent fail-open re-opens the H-1 monetization bypass).
"""

import logging

import httpx
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(1.5, connect=0.5)
_UNAVAILABLE = "Service temporarily unavailable. Please try again shortly."


async def check_access(
    *,
    tool_id: str,
    user_id: str,
    email: str = "",
    email_verified: bool = False,
) -> None:
    """Consume one AI entitlement for *user_id*. Raise on denial; return on allow.

    Raises ``HTTPException`` 402 (quota exhausted) or 503 (gate unreachable).
    """
    payload = {
        "tool_id": tool_id,
        "tool_type": "ai",
        "principal_type": "user",
        "user_id": user_id,
        "email": email,
        "email_verified": email_verified,
    }
    url = f"{settings.PAYMENTS_INTERNAL_URL}/internal/v1/check-access"
    headers = {"X-Internal-Secret": settings.INTERNAL_SHARED_SECRET}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except (httpx.HTTPError, OSError) as exc:
        logger.error(
            "entitlement gate unreachable (%s) — blocking AI tool %s", exc, tool_id
        )
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc

    if resp.status_code != 200:
        logger.error(
            "entitlement gate status %s — blocking AI tool %s",
            resp.status_code,
            tool_id,
        )
        raise HTTPException(status_code=503, detail=_UNAVAILABLE)

    data = resp.json()
    if not data.get("allowed", False):
        raise HTTPException(
            status_code=402,
            detail={
                "code": data.get("reason", "blocked"),
                "message": data.get("message")
                or "You've used your free AI quota. Buy credits or a pass to continue.",
            },
        )


__all__ = ["check_access"]
