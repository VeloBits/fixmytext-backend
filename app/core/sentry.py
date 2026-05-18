"""Sentry init + PII scrubber — thin shim over fixmytext_shared.

Re-exports the shared implementation and pre-binds the monolith's
``settings`` so the existing ``init_sentry()`` call site in ``main.py``
keeps its zero-argument signature.
"""

from app.core.config import settings
from fixmytext_shared.observability.sentry import (
    _PII_HEADERS,
    _PII_KEYS,
    _before_send,
)
from fixmytext_shared.observability.sentry import init_sentry as _init_sentry


def init_sentry() -> None:
    """Initialise Sentry SDK with the monolith's settings."""
    _init_sentry(settings)


__all__ = ["_PII_HEADERS", "_PII_KEYS", "_before_send", "init_sentry"]
