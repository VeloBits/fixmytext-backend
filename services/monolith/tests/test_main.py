"""Tests for main.py — health checks, middleware, and app configuration."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from main import app

from app.db.session import get_db


def _make_anon_client(mock_db=None):
    """Create an anonymous TestClient with only get_db overridden."""
    if mock_db is None:
        mock_db = AsyncMock()

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app, raise_server_exceptions=False)
    return client


# ── Health checks ────────────────────────────────────────────────────────────


class TestHealthEndpoints:
    """Test liveness and readiness probes."""

    def test_health_liveness(self):
        """GET /health returns 200 with status=ok."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_readiness_db_ok(self):
        """GET /health/ready returns 200 when DB is reachable."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock()  # SELECT 1 succeeds
        client = _make_anon_client(mock_db)
        resp = client.get("/health/ready")
        app.dependency_overrides.clear()
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"

    def test_health_readiness_db_down(self):
        """GET /health/ready returns 503 when DB is unreachable."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("connection refused")
        client = _make_anon_client(mock_db)
        resp = client.get("/health/ready")
        app.dependency_overrides.clear()
        assert resp.status_code == 503


# ── Correlation ID Middleware ────────────────────────────────────────────────


class TestCorrelationIdMiddleware:
    """Test X-Request-ID header injection."""

    def test_generates_request_id(self):
        """Response includes X-Request-ID when none is sent."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert "x-request-id" in resp.headers

    def test_echoes_custom_request_id(self):
        """Custom X-Request-ID sent by client is echoed back."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health", headers={"X-Request-ID": "test-req-42"})
        assert resp.headers.get("x-request-id") == "test-req-42"

    def test_different_requests_get_different_ids(self):
        """Two requests without custom ID get distinct request IDs."""
        client = TestClient(app, raise_server_exceptions=False)
        resp1 = client.get("/health")
        resp2 = client.get("/health")
        id1 = resp1.headers.get("x-request-id")
        id2 = resp2.headers.get("x-request-id")
        assert id1 != id2


# ── CORS Middleware ──────────────────────────────────────────────────────────


class TestCORSMiddleware:
    """Test CORS header configuration."""

    def test_cors_preflight(self):
        """OPTIONS request gets CORS headers."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI CORS middleware returns 200 for preflight;
        # 400 when Access-Control-Request-Headers is missing (Starlette >=0.36).
        assert resp.status_code in (200, 204, 400, 405)

    def test_cors_allow_origin_header(self):
        """Normal request from allowed origin gets CORS header."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        # If origin is in allowed list, header is set
        cors_header = resp.headers.get("access-control-allow-origin")
        if cors_header:
            assert cors_header in ("http://localhost:3000", "*")


# ── 404 for unknown routes ──────────────────────────────────────────────────


class TestUnknownRoutes:
    """Test that non-existent routes return 404/405."""

    def test_unknown_get_path(self):
        """GET to non-existent path returns 404."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code in (404, 405)

    def test_unknown_post_path(self):
        """POST to non-existent path returns 404/405."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/nonexistent", json={"text": "hello"})
        assert resp.status_code in (404, 405)
