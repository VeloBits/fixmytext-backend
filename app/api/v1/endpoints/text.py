"""
Text transformation API endpoints.

All tools are registered in ``app.core.tool_registry``.  This module provides
a single ``_execute_tool`` dispatcher that handles access control, rate
limiting, logging, and error handling for *every* tool.  Individual POST
routes are generated dynamically at import time so that backward
compatibility and per-tool OpenAPI docs are preserved.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_optional_user, get_verified_user
from app.core.rate_limit import ai_limiter
from app.core.sanitize import sanitize_log_value as _safe
from app.core.tool_registry import ToolType, get_all_tools, get_tool
from app.db.models import User
from app.db.session import get_db
from app.schemas.text import (
    CaesarRequest,
    FilterRequest,
    FormatRequest,
    KeyedCipherRequest,
    NthLineRequest,
    PadRequest,
    RailFenceRequest,
    SplitJoinRequest,
    SubstitutionRequest,
    TextRequest,
    TextResponse,
    ToneRequest,
    TranslateRequest,
    TruncateRequest,
    WrapRequest,
)
from app.services import ai_service
from app.services.pass_service import (
    check_tool_access,
    check_visitor_access,
    record_tool_discovery,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/text", tags=["Text"])

# Lookup table so ``_register_routes`` can resolve model names at runtime.
_REQUEST_MODELS: dict[str, type] = {
    "TextRequest": TextRequest,
    "CaesarRequest": CaesarRequest,
    "FilterRequest": FilterRequest,
    "FormatRequest": FormatRequest,
    "KeyedCipherRequest": KeyedCipherRequest,
    "NthLineRequest": NthLineRequest,
    "PadRequest": PadRequest,
    "RailFenceRequest": RailFenceRequest,
    "SplitJoinRequest": SplitJoinRequest,
    "SubstitutionRequest": SubstitutionRequest,
    "ToneRequest": ToneRequest,
    "TranslateRequest": TranslateRequest,
    "TruncateRequest": TruncateRequest,
    "WrapRequest": WrapRequest,
}


# ---------------------------------------------------------------------------
# Access-control helper
# ---------------------------------------------------------------------------


async def _enforce_tool_access(
    request: Request,
    tool_id: str,
    tool_type: str,
    user: User | None,
    db: AsyncSession,
) -> None:
    """Unified tool access check -- works for both authenticated and visitor users.

    Raises ``HTTPException(429)`` when the user has exhausted their daily
    allowance for *tool_id*.
    """
    if user:
        result = await check_tool_access(user, tool_id, tool_type, db)
    else:
        fingerprint = request.headers.get("x-visitor-id", "")
        ip = request.client.host if request.client else ""
        result = await check_visitor_access(fingerprint, ip, tool_id, tool_type, db)

    if not result["allowed"]:
        logger.warning(
            "ACCESS DENIED tool=%s type=%s user=%s reason=%s",
            _safe(tool_id),
            _safe(tool_type),
            str(user.id) if user else "visitor",
            _safe(result.get("message", "limit reached")),
        )
        raise HTTPException(
            status_code=429,
            detail=result.get(
                "message",
                "Daily limit reached. Get a pass for more access!",
            ),
        )

    # Record tool discovery for authenticated users (fire-and-forget).
    if user:
        await record_tool_discovery(user.id, tool_id, db)


# ---------------------------------------------------------------------------
# Extractors: pull per-tool extra arguments from the various request models
# ---------------------------------------------------------------------------


def _extract_extra_args(tool_id: str, req: Any) -> tuple[Any, ...]:
    """Return the extra positional arguments that *tool_id*'s handler needs.

    Most tools only need ``req.text``; this function extracts the *additional*
    fields (shift, key, delimiter, ...) for tools with specialised schemas.
    """
    # -- Cipher tools with extra params ----------------------------------
    if tool_id == "caesar-cipher":
        return (req.shift,)
    if tool_id in (
        "vigenere-encrypt",
        "vigenere-decrypt",
        "playfair-encrypt",
        "columnar-transposition",
    ):
        return (req.key,)
    if tool_id in ("rail-fence-encrypt", "rail-fence-decrypt"):
        return (req.rails,)
    if tool_id == "substitution-cipher":
        return (req.mapping,)

    # -- Text-tools with extra params ------------------------------------
    if tool_id in ("split-to-lines", "join-lines"):
        return (req.delimiter,)
    if tool_id == "pad-lines":
        return (req.align,)
    if tool_id == "wrap-lines":
        return (req.prefix, req.suffix)
    if tool_id in ("filter-lines", "remove-lines"):
        return (
            req.pattern,
            req.case_sensitive,
            req.use_regex,
            req.compiled_pattern,
        )
    if tool_id == "truncate-lines":
        return (req.max_length,)
    if tool_id == "extract-nth-lines":
        return (req.n, req.offset)

    # -- AI tools with extra params --------------------------------------
    if tool_id in ("translate", "transliterate"):
        return (req.target_language,)
    if tool_id == "change-tone":
        return (req.tone,)
    if tool_id == "change-format":
        return (req.format,)

    return ()


# ---------------------------------------------------------------------------
# Central dispatcher
# ---------------------------------------------------------------------------


async def _execute_tool(
    tool_id: str,
    request: Request,
    req: Any,
    user: User | None,
    db: AsyncSession,
) -> TextResponse:
    """Execute a text transformation tool by *tool_id*.

    Handles both local (sync, run-in-thread) and AI (async) tools together
    with access control, rate limiting, logging, and per-tool error handling.
    """
    tool = get_tool(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")

    # Authenticated users must verify their email before using any tool.
    # Unauthenticated visitors keep their free-tier access — the rule is only
    # meant to prevent a fresh, unverified signup from silently using tools
    # while we still don't know they own the inbox they registered with.
    if user is not None and not user.is_email_verified:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "email_not_verified",
                "message": (
                    "Please verify your email address to use FixMyText tools."
                ),
            },
        )

    client_ip = request.client.host if request.client else "unknown"
    user_id = str(user.id) if user else "visitor"
    kind = "AI    " if tool.tool_type == ToolType.AI else "LOCAL "

    logger.info(
        "%s op=%s user=%s ip=%s chars=%d",
        kind,
        _safe(tool_id),
        user_id,
        client_ip,
        len(req.text),
    )

    # -- Access control --------------------------------------------------
    access_type = "ai" if tool.tool_type == ToolType.AI else "api"
    if db:
        await _enforce_tool_access(request, tool_id, access_type, user, db)

    # -- Rate limiting (AI only) -----------------------------------------
    if tool.tool_type == ToolType.AI:
        await ai_limiter.check(request, user_id=str(user.id) if user else None)

    # -- Build the dynamic operation label for the response ---------------
    # Some AI endpoints historically used a dynamic operation label that
    # included a sub-parameter (e.g. "translate-spanish", "tone-formal",
    # "format-bullets").  We replicate that here for backward compat.
    operation = tool_id
    if tool_id in ("translate", "transliterate") and hasattr(req, "target_language"):
        operation = f"{tool_id}-{req.target_language.lower()}"
    elif tool_id == "change-tone" and hasattr(req, "tone"):
        operation = f"tone-{req.tone.lower()}"
    elif tool_id == "change-format" and hasattr(req, "format"):
        operation = f"format-{req.format.lower()}"

    extra_args = _extract_extra_args(tool_id, req)

    # -- Dispatch --------------------------------------------------------
    try:
        if tool.tool_type == ToolType.LOCAL:
            # Local tools are synchronous; run in a thread to keep the
            # event loop responsive.
            if extra_args:
                result = await asyncio.to_thread(tool.handler, req.text, *extra_args)
            else:
                result = await asyncio.to_thread(tool.handler, req.text)
        else:
            # AI tools are natively async.
            result = await ai_service.run_ai_tool(tool_id, req.text, *extra_args)

        logger.info("%s op=%s -> OK (%d chars)", kind, _safe(tool_id), len(result))
        return TextResponse(original=req.text, result=result, operation=operation)

    except HTTPException:
        # Re-raise FastAPI HTTP exceptions untouched.
        raise

    except Exception as exc:
        # Check if this exception matches one of the tool's known
        # user-facing error types (bad input for decode/parse tools).
        if tool.error_exceptions and isinstance(exc, tool.error_exceptions):
            detail = tool.error_detail or str(exc)
            raise HTTPException(status_code=400, detail=detail) from exc

        if tool.tool_type == ToolType.AI:
            # AI endpoints historically returned a generic 500 message.
            logger.exception("AI     op=%s -> FAILED: %s", _safe(tool_id), _safe(exc))
            raise HTTPException(
                status_code=500,
                detail=f"{tool.display_name} failed",
            ) from exc

        # Unexpected error on a local tool -- let it propagate.
        raise


# ---------------------------------------------------------------------------
# Dynamic route registration
# ---------------------------------------------------------------------------


def _register_routes() -> None:
    """Register a POST route for every tool in the registry.

    Each route has its own closure-captured *tool_id* so that FastAPI sees
    distinct handler functions with correct names and docstrings.
    """
    tools = get_all_tools()

    for tool_id, tool_def in tools.items():
        # Determine the request model for this tool.
        model_name = tool_def.request_model or "TextRequest"
        req_model = _REQUEST_MODELS[model_name]

        # Choose the auth dependency: AI tools require a logged-in user.
        if tool_def.requires_auth:
            _make_authed_route(tool_id, tool_def, req_model)
        else:
            _make_optional_route(tool_id, tool_def, req_model)


def _make_authed_route(tool_id: str, tool_def: Any, req_model: type) -> None:
    """Create a route that requires authentication (all AI tools).

    Email-verification enforcement lives in ``_execute_tool`` so both
    auth-required and optional-auth routes get the same treatment.
    """

    async def handler(
        request: Request,
        req: req_model,  # type: ignore[valid-type]
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> TextResponse:
        return await _execute_tool(tool_id, request, req, user, db)

    # Give each handler a unique __name__ so FastAPI can generate distinct
    # operation IDs for the OpenAPI schema.
    handler.__name__ = f"tool_{tool_id.replace('-', '_')}"
    handler.__doc__ = f"Apply the '{tool_id}' transformation to the input text."

    router.post(
        f"/{tool_id}",
        response_model=TextResponse,
        summary=tool_def.display_name,
        tags=[f"tools:{tool_def.category}"],
    )(handler)


def _make_optional_route(tool_id: str, tool_def: Any, req_model: type) -> None:
    """Create a route with optional authentication (all local tools)."""

    async def handler(
        request: Request,
        req: req_model,  # type: ignore[valid-type]
        user: User | None = Depends(get_optional_user),
        db: AsyncSession = Depends(get_db),
    ) -> TextResponse:
        return await _execute_tool(tool_id, request, req, user, db)

    handler.__name__ = f"tool_{tool_id.replace('-', '_')}"
    handler.__doc__ = f"Apply the '{tool_id}' transformation to the input text."

    router.post(
        f"/{tool_id}",
        response_model=TextResponse,
        summary=tool_def.display_name,
        tags=[f"tools:{tool_def.category}"],
    )(handler)


# Populate routes at module-import time so that ``router`` is ready before
# the main application mounts it.
_register_routes()


# ── SSE streaming endpoint for AI tools ──────────────────────────────────────


@router.post("/{tool_id}/stream", tags=["tools:ai-stream"])
async def stream_tool(
    tool_id: str,
    req: TextRequest,
    request: Request,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream AI tool output via Server-Sent Events (token-by-token).

    Only available for AI-type tools. Returns a ``text/event-stream`` response.
    """
    tool_def = get_tool(tool_id)
    if not tool_def or tool_def.tool_type != ToolType.AI:
        raise HTTPException(404, f"AI tool '{tool_id}' not found")

    # -- Access control (must match _execute_tool behaviour) ----------------
    await _enforce_tool_access(request, tool_id, "ai", user, db)

    await ai_limiter.check(request, user_id=str(user.id))

    extra_args = _extract_extra_args(tool_id, req)

    async def event_generator():
        try:
            async for token in ai_service.stream_ai_tool(
                tool_id, req.text, *extra_args
            ):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.exception("Stream error for tool=%s", tool_id)
            yield f"data: [ERROR] {exc}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
