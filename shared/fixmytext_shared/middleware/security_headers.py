"""SecurityHeadersMiddleware — adds standard security headers to every response.

HSTS is conditionally enabled via the ``is_production`` constructor argument
so the middleware doesn't need to read settings directly.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to every response.

    Args:
        app: ASGI app (handled by Starlette).
        is_production: when True, also emits Strict-Transport-Security.
    """

    def __init__(self, app, *, is_production: bool = False):
        super().__init__(app)
        self._is_production = is_production

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        if self._is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        return response
