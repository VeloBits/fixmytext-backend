"""RequestLoggingMiddleware - logs method, path, status, duration, request_id."""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status code, duration, and request ID.

    Uses ``request.state.request_id`` populated by ``CorrelationIdMiddleware``.
    Logger name is configurable via the constructor; defaults to the module
    logger so monolith and services share a consistent output stream.
    """

    def __init__(self, app, *, logger_name: str = "fixmytext"):
        super().__init__(app)
        self._logger = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        path = request.url.path
        query = str(request.url.query)
        request_id = getattr(request.state, "request_id", "N/A")

        self._logger.info(
            "%s %s%s from %s [req_id=%s]",
            method,
            path,
            f"?{query}" if query else "",
            client_ip,
            request_id,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.error(
                "%s %s -> 500 (%.1fms) [req_id=%s] ERROR: %s",
                method,
                path,
                duration_ms,
                request_id,
                exc,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        self._logger.info(
            "%s %s -> %s (%.1fms) [req_id=%s]",
            method,
            path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
