"""Log sanitisation + PII redaction filters.

`LogSanitizationFilter` strips ASCII control characters (anti-injection).
`PiiRedactionFilter` blanks out log records whose message mentions a
PII key (text, prompt, password, token, cookie, authorization).

Both attach to a `logging.Handler` via `handler.addFilter(...)`.
"""

import logging
import re

# Matches ASCII control characters that can be used for log injection
# (newlines, carriage returns, and other C0 controls except tab).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")


_PII_PATTERN_KEYS = frozenset(
    {
        "text",
        "prompt",
        "password",
        "token",
        "cookie",
        "authorization",
    }
)


def sanitize_log_value(value: object) -> str:
    """Sanitise *value* for safe inclusion in log messages.

    Replaces newlines, carriage returns, and other ASCII control characters
    with a space so attackers cannot forge new log entries.
    """
    return _CONTROL_CHAR_RE.sub(" ", str(value))


def _sanitize_arg(arg: object) -> object:
    if isinstance(arg, str):
        return _CONTROL_CHAR_RE.sub(" ", arg)
    return arg


class LogSanitizationFilter(logging.Filter):
    """Strip control characters from all log output (anti-injection)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _CONTROL_CHAR_RE.sub(" ", record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _sanitize_arg(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_sanitize_arg(a) for a in record.args)
        return True


class PiiRedactionFilter(logging.Filter):
    """Redact log records whose message mentions a PII key."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for key in _PII_PATTERN_KEYS:
                if key in record.msg.lower():
                    record.msg = "[REDACTED]"
                    record.args = ()
                    return True
        return True
