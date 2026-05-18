"""Log sanitisation — thin shim over fixmytext_shared.

The actual implementation lives in ``fixmytext_shared.observability.sanitize``.
Kept as a shim so existing imports from ``app.core.sanitize`` continue to work
during the strangler-fig migration.
"""

from fixmytext_shared.observability.sanitize import (
    LogSanitizationFilter,
    sanitize_log_value,
)

__all__ = ["LogSanitizationFilter", "sanitize_log_value"]
