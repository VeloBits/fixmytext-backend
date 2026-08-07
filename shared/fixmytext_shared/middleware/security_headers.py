"""SecurityHeadersMiddleware - adds standard security headers to every response.

HSTS is conditionally enabled via the ``is_production`` constructor argument
so the middleware doesn't need to read settings directly.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Strict default for the JSON API surface: block every sub-resource origin.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"

# Interactive API docs (Swagger UI / ReDoc) load their bundle, styles, favicon
# and an inline init script from a CDN, and fetch the OpenAPI schema same-origin.
# These pages are only served in non-production (``docs_url``/``redoc_url`` are
# ``None`` otherwise), so the relaxation below never applies to a prod deployment.
_DOCS_PATHS = frozenset({"/docs", "/redoc"})
_DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


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
        # API responses stay locked down; only the dev-only docs pages get the
        # CDN/inline allowances Swagger UI and ReDoc need to render.
        if not self._is_production and request.url.path in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = _DOCS_CSP
        else:
            response.headers["Content-Security-Policy"] = _API_CSP
        if self._is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        return response
