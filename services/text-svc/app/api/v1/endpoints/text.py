"""
Text transformation API endpoint for text-svc.

Serves all LOCAL (non-AI) text transformation tools at
``POST /api/v1/text/{tool_id}``.

Design decisions:
- No quota check at the endpoint level (enforced in pass_service).
- No tool discovery recording (no DB).
- Optional auth — requests are accepted with or without JWT.
  User ID is extracted from JWT only if present (for logging).
- Sync handlers run in a thread via ``asyncio.to_thread``.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

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
from app.services.text_service import RegexTimeoutError
from app.tool_registry import ToolType, get_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/text", tags=["Text"])

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
) -> TextResponse:
    """Execute a LOCAL text transformation tool by *tool_id*."""
    tool = get_tool(tool_id)
    if tool is None or tool.tool_type != ToolType.LOCAL:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")

    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        "LOCAL op=%s ip=%s chars=%d",
        tool_id,
        client_ip,
        len(req.text),
    )

    extra_args = _extract_extra_args(tool_id, req)

    try:
        result = await asyncio.to_thread(tool.handler, req.text, *extra_args)
        logger.info("LOCAL op=%s -> OK (%d chars)", tool_id, len(result))
        return TextResponse(original=req.text, result=result, operation=tool_id)

    except HTTPException:
        raise

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
    ) -> TextResponse:
        return await _execute_tool(tool_id, request, req)

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
