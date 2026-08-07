"""Domain exceptions raised by shared utilities. Services translate to HTTP."""


class AuthError(Exception):
    """Authentication failure - invalid/expired token, missing claims, etc."""


class RateLimitError(Exception):
    """Rate-limit threshold exceeded."""


class ConfigError(Exception):
    """Misconfiguration - missing required env var, invalid setting."""
