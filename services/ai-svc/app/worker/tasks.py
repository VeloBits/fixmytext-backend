"""
arq worker tasks for async Groq AI calls.

The ``run_ai_tool`` task mirrors the logic of the synchronous
``POST /api/v1/ai/{tool_id}`` endpoint but runs inside the arq worker
process so long-running Groq calls never block an ASGI worker.

WorkerSettings is the arq entrypoint; the ``ai-worker`` Docker service
starts with::

    python -m arq app.worker.main.WorkerSettings
"""

import logging
from typing import Any

from arq.connections import RedisSettings

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Startup / shutdown hooks ──────────────────────────────────────────────────


async def startup(ctx: dict) -> None:
    """Initialize Groq client once per worker process."""
    from app.services.ai_service import init_groq_client

    init_groq_client()
    logger.info("arq worker: Groq client initialised")


async def shutdown(ctx: dict) -> None:
    """Cleanly close the Groq client when the worker exits."""
    from app.services.ai_service import close_groq_client

    await close_groq_client()
    logger.info("arq worker: Groq client closed")


# ── Task ──────────────────────────────────────────────────────────────────────


async def run_ai_tool(
    ctx: dict,
    tool_id: str,
    input_text: str,
    user_sub: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """arq task: execute an AI tool and return a result dict.

    Parameters
    ----------
    ctx:
        arq job context (injected automatically).
    tool_id:
        Registered AI tool slug, e.g. ``"fix-grammar"``, ``"translate"``.
    input_text:
        The user's input text.
    user_sub:
        Keycloak subject UUID — stored for audit/logging; not used to
        perform any auth here (auth happened in the HTTP layer before the
        job was enqueued).
    options:
        Optional per-tool parameters:
          - ``target_language`` — for ``translate`` / ``transliterate``
          - ``tone``            — for ``change-tone``
          - ``format``          — for ``change-format``

    Returns
    -------
    dict with keys ``original``, ``result``, ``operation``.
    """
    from app.services import ai_service
    from app.tool_registry import get_tool

    opts = options or {}

    tool_def = get_tool(tool_id)
    if tool_def is None:
        raise ValueError(f"AI tool '{tool_id}' not found")

    # Build extra args from options (mirrors _extract_extra_args in the router)
    extra_args: tuple[Any, ...] = ()
    if tool_id in ("translate", "transliterate") and opts.get("target_language"):
        extra_args = (opts["target_language"],)
    elif tool_id == "change-tone" and opts.get("tone"):
        extra_args = (opts["tone"],)
    elif tool_id == "change-format" and opts.get("format"):
        extra_args = (opts["format"],)

    # Build operation label (same logic as the HTTP endpoint)
    operation = tool_id
    if tool_id in ("translate", "transliterate") and extra_args:
        operation = f"{tool_id}-{extra_args[0].lower()}"
    elif tool_id == "change-tone" and extra_args:
        operation = f"tone-{extra_args[0].lower()}"
    elif tool_id == "change-format" and extra_args:
        operation = f"format-{extra_args[0].lower()}"

    logger.info(
        "WORKER op=%s user=%s chars=%d",
        tool_id,
        user_sub,
        len(input_text),
    )

    result_text = await ai_service.run_ai_tool(tool_id, input_text, *extra_args)

    logger.info("WORKER op=%s -> OK (%d chars)", tool_id, len(result_text))
    return {
        "original": input_text,
        "result": result_text,
        "operation": operation,
    }


# ── Worker configuration ──────────────────────────────────────────────────────


class WorkerSettings:
    """arq WorkerSettings — passed to ``arq.run_worker`` or ``python -m arq``."""

    functions = [run_ai_tool]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(
        settings.REDIS_URL or "redis://redis-service:6379/0"
    )
    # Keep job results in Redis for 1 hour so callers can poll /jobs/{job_id}
    keep_result = 3600
    # Allow up to 120 s per Groq call (Groq timeout is 35 s + buffer)
    job_timeout = 120
