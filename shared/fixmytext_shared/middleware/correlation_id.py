"""CorrelationIdMiddleware - sets/echoes X-Request-ID on every request."""

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Inject ``X-Request-ID`` into request state and response headers.

    If the incoming request already carries an ``X-Request-ID`` header the
    value is reused; otherwise a new UUID4 is generated.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
