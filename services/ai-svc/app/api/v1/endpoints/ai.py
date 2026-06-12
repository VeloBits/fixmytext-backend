"""
AI text transformation endpoints.

Serves ``POST /api/v1/ai/{tool_id}`` and ``POST /api/v1/ai/{tool_id}/stream``.

Auth: RS256 JWT verified via Keycloak JWKS — no DB lookup (stateless).
Rate limiting: shared ``rl:ai`` prefix in Redis (cross-service with monolith).
"""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel

from app.core.config import settings
from app.core.rate_limit import ai_limiter
from app.services import ai_service
from app.services.entitlement_client import check_access as check_entitlement
from app.tool_registry import get_tool

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: str) -> str:
    """Strip CR/LF from user-controlled values to prevent log injection."""
    return str(value).replace("\r", "").replace("\n", "")


router = APIRouter(prefix="/ai", tags=["AI"])

# ── Request / response schemas ────────────────────────────────────────────────


class TextRequest(BaseModel):
    text: str


class TranslateRequest(BaseModel):
    text: str
    target_language: str


class ToneRequest(BaseModel):
    text: str
    tone: str


class FormatRequest(BaseModel):
    text: str
    format: str


class TextResponse(BaseModel):
    original: str
    result: str
    operation: str


# ── Auth: lightweight JWT-only (no DB) ────────────────────────────────────────


@dataclass
class AuthenticatedUser:
    """Lightweight user identity extracted from a verified Keycloak JWT.

    ai-svc has no database — identity is JWT-only.
    """

    id: str  # Keycloak sub (UUID string)
    email: str
    is_email_verified: bool


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """Verify Keycloak JWT and return a lightweight AuthenticatedUser.

    Raises 401 when no credentials are present or the token is invalid.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        from fixmytext_shared.security.jwt import verify_jwt_raw

        payload = verify_jwt_raw(
            credentials.credentials,
            algorithm="RS256",
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            audience=settings.KEYCLOAK_AUDIENCE or None,
        )
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Token expired or invalid") from exc
    return AuthenticatedUser(
        id=payload.get("sub", ""),
        email=payload.get("email", ""),
        is_email_verified=bool(payload.get("email_verified", False)),
    )


async def get_verified_user(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Extend get_current_user with email-verification gate.

    Returns 403 with a machine-readable code so the frontend can prompt the
    user to verify without treating it as a generic auth failure.
    """
    if not user.is_email_verified:
        logger.info("AUTH   user=%s blocked: email not verified", user.id)
        raise HTTPException(
            status_code=403,
            detail={
                "code": "email_not_verified",
                "message": "Please verify your email to use AI tools.",
            },
        )
    return user


# ── Extra-args extractor ──────────────────────────────────────────────────────


def _extract_extra_args(tool_id: str, req: Any) -> tuple[Any, ...]:
    """Return the extra positional arguments for parameterised AI tools."""
    if tool_id in ("translate", "transliterate"):
        return (req.target_language,)
    if tool_id == "change-tone":
        return (req.tone,)
    if tool_id == "change-format":
        return (req.format,)
    return ()


# ── Request model lookup ──────────────────────────────────────────────────────

_REQUEST_MODELS: dict[str, type] = {
    "translate": TranslateRequest,
    "transliterate": TranslateRequest,
    "change-tone": ToneRequest,
    "change-format": FormatRequest,
}


# ── Endpoint: POST /api/v1/ai/{tool_id} ──────────────────────────────────────


@router.post("/{tool_id}", response_model=TextResponse)
async def run_ai_tool(
    tool_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_verified_user),
) -> TextResponse:
    """Execute an AI text transformation tool.

    All registered AI tools are available here.  Parameterised tools
    (translate, change-tone, change-format) expect additional fields in
    the request body.
    """
    tool_def = get_tool(tool_id)
    if tool_def is None:
        raise HTTPException(status_code=404, detail=f"AI tool '{tool_id}' not found")

    # Parse the correct request model for this tool
    req_model = _REQUEST_MODELS.get(tool_id, TextRequest)
    try:
        body = await request.json()
        req = req_model(**body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    safe_op = _sanitize_for_log(tool_id)
    logger.info(
        "AI     op=%s user=%s chars=%d",
        safe_op,
        user.id,
        len(req.text),
    )

    # Rate limiting first (cheap), then the per-tool entitlement check (H-1):
    # consumes credits/passes/free quota, fails closed if payments-svc is down.
    await ai_limiter.check(request, user_id=user.id)
    await check_entitlement(
        tool_id=tool_id,
        user_id=user.id,
        email=user.email,
        email_verified=user.is_email_verified,
    )

    # Build operation label (include sub-param for parameterised tools)
    operation = tool_id
    if tool_id in ("translate", "transliterate") and hasattr(req, "target_language"):
        operation = f"{tool_id}-{req.target_language.lower()}"
    elif tool_id == "change-tone" and hasattr(req, "tone"):
        operation = f"tone-{req.tone.lower()}"
    elif tool_id == "change-format" and hasattr(req, "format"):
        operation = f"format-{req.format.lower()}"

    extra_args = _extract_extra_args(tool_id, req)

    try:
        result = await ai_service.run_ai_tool(tool_id, req.text, *extra_args)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AI     op=%s -> FAILED: %s", safe_op, exc)
        raise HTTPException(
            status_code=500,
            detail=f"{tool_def.display_name} failed",
        ) from exc

    logger.info("AI     op=%s -> OK (%d chars)", safe_op, len(result))
    return TextResponse(original=req.text, result=result, operation=operation)


# ── Endpoint: POST /api/v1/ai/{tool_id}/stream ───────────────────────────────


@router.post("/{tool_id}/stream", tags=["AI Stream"])
async def stream_ai_tool(
    tool_id: str,
    req: TextRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_verified_user),
) -> StreamingResponse:
    """Stream AI tool output via Server-Sent Events (token-by-token).

    Returns a ``text/event-stream`` response. Only available for registered
    AI tools.
    """
    tool_def = get_tool(tool_id)
    if tool_def is None:
        raise HTTPException(status_code=404, detail=f"AI tool '{tool_id}' not found")

    await ai_limiter.check(request, user_id=user.id)
    await check_entitlement(
        tool_id=tool_id,
        user_id=user.id,
        email=user.email,
        email_verified=user.is_email_verified,
    )

    extra_args = _extract_extra_args(tool_id, req)

    async def event_generator():
        try:
            async for token in ai_service.stream_ai_tool(
                tool_id, req.text, *extra_args
            ):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            # Do not expose exc (stack trace) to the client — log it server-side only.
            logger.exception("Stream error for tool=%s", _sanitize_for_log(tool_id))
            yield "data: [ERROR] Internal server error\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
