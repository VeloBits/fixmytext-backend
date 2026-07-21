"""Client for the payments-svc entitlement gate (ai-svc).

Calls ``POST /internal/v1/check-access`` after the rate-limit check and before
invoking the model. ai-svc requests are always authenticated and every AI tool
is billable, so a gate outage fails CLOSED (503) — there is no free fallback
(the M-4 lesson: a silent fail-open re-opens the H-1 monetization bypass).
"""

import logging

import httpx
from fastapi import HTTPException
from fixmytext_shared.observability import sanitize_log_value

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(1.5, connect=0.5)
_UNAVAILABLE = "Service temporarily unavailable. Please try again shortly."

# Shared persistent client — reuses TCP connections across requests.
# Initialized by init_http_client() in the FastAPI lifespan.
_HTTP_CLIENT: httpx.AsyncClient | None = None


def init_http_client() -> None:
    """Open the shared HTTP client (call once from FastAPI lifespan)."""
    global _HTTP_CLIENT
    _HTTP_CLIENT = httpx.AsyncClient(timeout=_TIMEOUT)


async def close_http_client() -> None:
    """Close the shared HTTP client (call from FastAPI lifespan on shutdown)."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None:
        await _HTTP_CLIENT.aclose()
        _HTTP_CLIENT = None


def _get_http_client() -> httpx.AsyncClient:
    """Return the shared client, creating it lazily if lifespan init was skipped."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient(timeout=_TIMEOUT)
    return _HTTP_CLIENT


async def check_entitlement(
    *,
    tool_id: str,
    user_id: str,
    email: str = "",
    email_verified: bool = False,
) -> None:
    """Consume one AI entitlement for *user_id*. Raise on denial; return on allow.

    Raises ``HTTPException`` 402 (quota exhausted) or 503 (gate unreachable).

    Deliberately NOT named ``check_access`` like text-svc's client: CodeQL merges
    same-dotted-path modules (``app.services.entitlement_client``) across services
    and cross-validates call signatures, producing false alerts. Keep the name unique.
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
        resp = await _get_http_client().post(url, json=payload, headers=headers)
    except (httpx.HTTPError, OSError) as exc:
        logger.error(
            "entitlement gate unreachable (%s) — blocking AI tool %s",
            sanitize_log_value(exc),
            sanitize_log_value(tool_id),
        )
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc

    if resp.status_code != 200:
        logger.error(
            "entitlement gate status %s — blocking AI tool %s",
            resp.status_code,
            sanitize_log_value(tool_id),
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


__all__ = ["check_entitlement", "init_http_client", "close_http_client"]
