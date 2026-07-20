"""Tests for shared ASGI middleware (correlation ID, security headers, logging)."""

import logging
import uuid

import httpx
import pytest
from fastapi import FastAPI, Request

from fixmytext_shared.middleware import (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)

_API_CSP = "default-src 'none'; frame-ancestors 'none'"


def _build_app(*middleware) -> FastAPI:
    """Build a minimal FastAPI app with the given (class, options) middleware."""
    app = FastAPI()
    for middleware_class, options in middleware:
        app.add_middleware(middleware_class, **options)

    @app.get("/ping")
    async def ping(request: Request):
        return {"request_id": getattr(request.state, "request_id", None)}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    return app


def _client_for(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


class TestCorrelationIdMiddleware:
    async def test_generates_request_id_when_absent(self):
        app = _build_app((CorrelationIdMiddleware, {}))
        async with _client_for(app) as client:
            resp = await client.get("/ping")
        assert resp.status_code == 200
        header = resp.headers["X-Request-ID"]
        uuid.UUID(header)  # generated IDs are valid UUIDs
        assert resp.json()["request_id"] == header

    async def test_echoes_incoming_request_id(self):
        app = _build_app((CorrelationIdMiddleware, {}))
        async with _client_for(app) as client:
            resp = await client.get("/ping", headers={"X-Request-ID": "req-abc-123"})
        assert resp.headers["X-Request-ID"] == "req-abc-123"
        assert resp.json()["request_id"] == "req-abc-123"


class TestSecurityHeadersMiddleware:
    async def test_standard_headers_on_api_response(self):
        app = _build_app((SecurityHeadersMiddleware, {"is_production": False}))
        async with _client_for(app) as client:
            resp = await client.get("/ping")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert (
            resp.headers["Permissions-Policy"]
            == "camera=(), microphone=(), geolocation=()"
        )
        assert resp.headers["Content-Security-Policy"] == _API_CSP
        assert "Strict-Transport-Security" not in resp.headers

    async def test_docs_get_relaxed_csp_outside_production(self):
        app = _build_app((SecurityHeadersMiddleware, {"is_production": False}))
        async with _client_for(app) as client:
            resp = await client.get("/docs")
        csp = resp.headers["Content-Security-Policy"]
        assert "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; " in csp
        assert "frame-ancestors 'none'" in csp

    async def test_docs_keep_strict_csp_in_production(self):
        app = _build_app((SecurityHeadersMiddleware, {"is_production": True}))
        async with _client_for(app) as client:
            resp = await client.get("/docs")
        assert resp.headers["Content-Security-Policy"] == _API_CSP

    async def test_hsts_emitted_only_in_production(self):
        app = _build_app((SecurityHeadersMiddleware, {"is_production": True}))
        async with _client_for(app) as client:
            resp = await client.get("/ping")
        assert (
            resp.headers["Strict-Transport-Security"]
            == "max-age=31536000; includeSubDomains; preload"
        )


class TestRequestLoggingMiddleware:
    async def test_logs_request_and_response(self, caplog):
        app = _build_app((RequestLoggingMiddleware, {}))
        with caplog.at_level(logging.INFO, logger="fixmytext"):
            async with _client_for(app) as client:
                resp = await client.get("/ping", params={"q": "1"})
        assert resp.status_code == 200
        messages = [r.getMessage() for r in caplog.records if r.name == "fixmytext"]
        assert any("GET /ping?q=1" in m for m in messages)
        assert any("-> 200" in m for m in messages)
        # No CorrelationIdMiddleware in front -> request_id falls back to N/A
        assert any("[req_id=N/A]" in m for m in messages)

    async def test_custom_logger_name(self, caplog):
        app = _build_app((RequestLoggingMiddleware, {"logger_name": "custom.access"}))
        with caplog.at_level(logging.INFO, logger="custom.access"):
            async with _client_for(app) as client:
                await client.get("/ping")
        assert any(r.name == "custom.access" for r in caplog.records)

    async def test_uses_request_id_set_by_correlation_middleware(self, caplog):
        # CorrelationIdMiddleware added last -> runs outermost, sets state first.
        app = _build_app(
            (RequestLoggingMiddleware, {}),
            (CorrelationIdMiddleware, {}),
        )
        with caplog.at_level(logging.INFO, logger="fixmytext"):
            async with _client_for(app) as client:
                await client.get("/ping", headers={"X-Request-ID": "trace-42"})
        messages = [r.getMessage() for r in caplog.records if r.name == "fixmytext"]
        assert any("[req_id=trace-42]" in m for m in messages)

    async def test_error_path_logs_500_and_reraises(self, caplog):
        app = _build_app((RequestLoggingMiddleware, {}))
        with caplog.at_level(logging.INFO, logger="fixmytext"):
            async with _client_for(app) as client:
                with pytest.raises(RuntimeError, match="kaboom"):
                    await client.get("/boom")
        error_messages = [
            r.getMessage()
            for r in caplog.records
            if r.name == "fixmytext" and r.levelno == logging.ERROR
        ]
        assert any("-> 500" in m and "kaboom" in m for m in error_messages)
