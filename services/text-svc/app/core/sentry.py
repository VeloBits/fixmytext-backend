"""Sentry init - thin shim over fixmytext_shared.

Re-exports the shared implementation and pre-binds text-svc's ``settings``
so the ``init_sentry()`` call site in ``main.py`` keeps a zero-argument
signature.
"""

from fixmytext_shared.observability.sentry import (
    _PII_HEADERS,
    _PII_KEYS,
    _before_send,
)
from fixmytext_shared.observability.sentry import init_sentry as _init_sentry

from app.core.config import settings


def init_sentry() -> None:
    """Initialise Sentry SDK with text-svc's settings."""
    _init_sentry(settings)


__all__ = ["_PII_HEADERS", "_PII_KEYS", "_before_send", "init_sentry"]
