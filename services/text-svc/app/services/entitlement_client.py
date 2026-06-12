"""Client for the payments-svc entitlement gate.

Calls ``POST /internal/v1/check-access`` before running a tool. Fails CLOSED for
non-free tools when the gate is unreachable (the M-4 lesson — a silent fail-open
re-opens the H-1 bypass): a gate outage degrades billable tools (503) but still
serves always-free tools from a local allowlist.
"""

import logging

import httpx
from fastapi import HTTPException, Request

from app.core.auth import OptionalUser
from app.core.config import settings

logger = logging.getLogger(__name__)

# Degraded-mode allowlist used ONLY when the gate is unreachable. Source of
# truth is payments-svc app/core/pass_catalog.py::ALWAYS_FREE_TOOL_IDS — keep in
# sync. When the gate IS reachable it makes the always-free decision itself.
ALWAYS_FREE_TOOL_IDS = frozenset(
    {"find_replace", "compare", "random_text", "password", "regex_test"}
)

_TIMEOUT = httpx.Timeout(1.5, connect=0.5)


def client_ip(request: Request) -> str:
    """Best-effort real client IP (first X-Forwarded-For hop, else peer)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _fail_closed(tool_id: str, tool_type: str, reason: str) -> None:
    """Allow only always-free tools when the gate is unreachable; else 503."""
    if tool_id in ALWAYS_FREE_TOOL_IDS or tool_type == "drawer":
        logger.warning(
            "entitlement gate unavailable (%s) — serving free tool %s", reason, tool_id
        )
        return
    logger.error(
        "entitlement gate unavailable (%s) — blocking billable tool %s",
        reason,
        tool_id,
    )
    raise HTTPException(
        status_code=503,
        detail="Service temporarily unavailable. Please try again shortly.",
    )


async def check_access(
    *,
    tool_id: str,
    tool_type: str,
    request: Request,
    user: OptionalUser | None = None,
) -> None:
    """Consume one tool entitlement. Raise on denial; return on allow.

    Raises ``HTTPException`` 402 (quota exhausted), or 503 (gate unreachable and
    the tool is billable).
    """
    payload: dict = {"tool_id": tool_id, "tool_type": tool_type}
    if user is not None:
        payload.update(
            principal_type="user",
            user_id=user.id,
            email=user.email,
            email_verified=user.is_email_verified,
        )
    else:
        payload.update(
            principal_type="visitor",
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )

    url = f"{settings.PAYMENTS_INTERNAL_URL}/internal/v1/check-access"
    headers = {"X-Internal-Secret": settings.INTERNAL_SHARED_SECRET}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except (httpx.HTTPError, OSError) as exc:
        _fail_closed(tool_id, tool_type, f"unreachable: {exc}")
        return

    if resp.status_code != 200:
        _fail_closed(tool_id, tool_type, f"status {resp.status_code}")
        return

    data = resp.json()
    if not data.get("allowed", False):
        raise HTTPException(
            status_code=402,
            detail={
                "code": data.get("reason", "blocked"),
                "message": data.get("message")
                or "Free limit reached for this tool. Sign in or buy a pass.",
            },
        )
