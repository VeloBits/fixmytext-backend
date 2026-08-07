"""
Text transformation API endpoint for text-svc.

Serves all LOCAL (non-AI) text transformation tools at
``POST /api/v1/text/{tool_id}``.

Design decisions:
- Per-tool quota/entitlement is enforced by calling payments-svc
  ``/internal/v1/check-access`` before running the tool; rate limiting (Redis,
  ``rl:text``) runs first so a throttled request never consumes quota.
- No tool discovery recording (no DB).
- Optional auth - requests are accepted with or without a JWT. When a valid
  token is present the caller is an authenticated user, else an anonymous
  visitor (each has its own quota).
- Sync handlers run in a worker thread via ``asyncio.to_thread`` under a hard
  wall-clock timeout.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auth import OptionalUser, get_optional_user
from app.core.rate_limit import text_limiter
from app.schemas.text import (
    CaesarRequest,
    FilterRequest,
    KeyedCipherRequest,
    NthLineRequest,
    PadRequest,
    RailFenceRequest,
    SplitJoinRequest,
    SubstitutionRequest,
    TextRequest,
    TextResponse,
    TruncateRequest,
    WrapRequest,
)
from app.services.entitlement_client import check_access as check_entitlement
from app.services.entitlement_client import client_ip
from app.services.text_service import RegexTimeoutError
from app.tool_registry import ToolType, get_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/text", tags=["Text"])

# Hard per-request wall-clock cap on a tool handler running in a worker thread.
# A thread can't be force-cancelled, so CPU-heavy tools (e.g. brainfuck) also
# bound themselves internally; this frees the request promptly either way.
_TOOL_EXEC_TIMEOUT_SECONDS = 5.0

# Lookup table so ``_register_routes`` can resolve model names at runtime.
_REQUEST_MODELS: dict[str, type] = {
    "TextRequest": TextRequest,
    "CaesarRequest": CaesarRequest,
    "FilterRequest": FilterRequest,
    "KeyedCipherRequest": KeyedCipherRequest,
    "NthLineRequest": NthLineRequest,
    "PadRequest": PadRequest,
    "RailFenceRequest": RailFenceRequest,
    "SplitJoinRequest": SplitJoinRequest,
    "SubstitutionRequest": SubstitutionRequest,
    "TruncateRequest": TruncateRequest,
    "WrapRequest": WrapRequest,
}


# ---------------------------------------------------------------------------
# Extractors: pull per-tool extra arguments from the various request models
# ---------------------------------------------------------------------------


def _extract_extra_args(tool_id: str, req: Any) -> tuple[Any, ...]:  # noqa: C901
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

    return ()


# ---------------------------------------------------------------------------
# Central dispatcher
# ---------------------------------------------------------------------------


async def _execute_tool(
    tool_id: str,
    request: Request,
    req: Any,
    user: OptionalUser | None,
) -> TextResponse:
    """Execute a LOCAL text transformation tool by *tool_id*.

    Order of guards: rate limit first (cheap, Redis), then the per-tool
    entitlement check against payments-svc (a DB write) - so a throttled request
    never consumes quota. Both run before the handler executes.
    """
    tool = get_tool(tool_id)
    if tool is None or tool.tool_type != ToolType.LOCAL:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")

    ip = client_ip(request)

    # 1) Rate limit - key by user when authenticated, else by client IP (H-4).
    rl_key = user.id if user is not None else f"visitor:{ip}"
    await text_limiter.check(request, user_id=rl_key)

    # 2) Per-tool entitlement / quota (H-1). Raises 402/503 on denial.
    await check_entitlement(
        tool_id=tool_id,
        tool_type=str(tool.tool_type),
        request=request,
        user=user,
    )

    logger.info("LOCAL op=%s ip=%s chars=%d", tool_id, ip, len(req.text))

    extra_args = _extract_extra_args(tool_id, req)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(tool.handler, req.text, *extra_args),
            timeout=_TOOL_EXEC_TIMEOUT_SECONDS,
        )
        logger.info("LOCAL op=%s -> OK (%d chars)", tool_id, len(result))
        return TextResponse(original=req.text, result=result, operation=tool_id)

    except HTTPException:
        raise

    except TimeoutError as exc:
        logger.warning(
            "LOCAL op=%s -> TIMEOUT (>%ss)", tool_id, _TOOL_EXEC_TIMEOUT_SECONDS
        )
        raise HTTPException(
            status_code=400,
            detail="Input too expensive to process - please reduce its size.",
        ) from exc

    except RegexTimeoutError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        if tool.error_exceptions and isinstance(exc, tool.error_exceptions):
            detail = tool.error_detail or str(exc)
            raise HTTPException(status_code=400, detail=detail) from exc
        raise


# ---------------------------------------------------------------------------
# Dynamic route registration
# ---------------------------------------------------------------------------


def _register_routes() -> None:
    """Register a POST route for every LOCAL tool in the registry."""
    from app.tool_registry import get_all_tools

    tools = get_all_tools()

    for tool_id, tool_def in tools.items():
        model_name = tool_def.request_model or "TextRequest"
        req_model = _REQUEST_MODELS[model_name]
        _make_route(tool_id, tool_def, req_model)


def _make_route(tool_id: str, tool_def: Any, req_model: type) -> None:
    """Create a POST route for a single LOCAL tool."""

    async def handler(
        request: Request,
        req: req_model,  # type: ignore[valid-type]
        user: OptionalUser | None = Depends(get_optional_user),
    ) -> TextResponse:
        return await _execute_tool(tool_id, request, req, user)

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
