"""OTel logs init + PII redaction filter — thin shim over fixmytext_shared.

Re-exports the shared implementation and pre-binds the monolith's
``settings`` so existing call sites keep their zero-argument signatures.
"""

from app.core.config import settings
from fixmytext_shared.observability.logs import (
    init_logs_otel as _init_logs_otel,
)
from fixmytext_shared.observability.logs import (
    shutdown_logs_otel,
)
from fixmytext_shared.observability.sanitize import PiiRedactionFilter


def init_logs_otel() -> None:
    """Configure OTel logs export using the monolith's settings."""
    _init_logs_otel(settings)


__all__ = ["PiiRedactionFilter", "init_logs_otel", "shutdown_logs_otel"]
