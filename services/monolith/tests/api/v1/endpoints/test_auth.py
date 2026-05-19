"""Tests for /api/v1/auth/me endpoint (the only remaining auth endpoint post-Keycloak cutover)."""

from fastapi.testclient import TestClient
from main import app

from app.core.deps import get_current_user
from app.db.session import get_db

# ── /auth/me ─────────────────────────────────────────────────────────────────


def test_me_returns_user(fake_user, mock_db):
    async def _get_db():
        yield mock_db

    async def _get_current_user():
        return fake_user

    mock_db.execute.return_value.scalar.return_value = None  # no pro subscription

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    resp = TestClient(app, raise_server_exceptions=True).get("/api/v1/auth/me")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == fake_user.email
    assert data["display_name"] == fake_user.display_name


def test_me_no_auth():
    resp = TestClient(app, raise_server_exceptions=False).get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_response_shape(fake_user, mock_db):
    """Validate response schema includes all expected fields."""

    async def _get_db():
        yield mock_db

    async def _get_current_user():
        return fake_user

    mock_db.execute.return_value.scalar.return_value = None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    resp = TestClient(app, raise_server_exceptions=True).get("/api/v1/auth/me")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "email" in data
    assert "display_name" in data
    assert "is_email_verified" in data
    assert "subscription_tier" in data
