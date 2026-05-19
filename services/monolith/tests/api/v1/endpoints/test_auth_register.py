"""Tests for /auth/register endpoint."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from main import app


def test_register_success():
    with (
        patch(
            "app.api.v1.endpoints.auth_register.create_keycloak_user",
            new=AsyncMock(return_value="kc-id-123"),
        ),
        patch(
            "app.api.v1.endpoints.auth_register.send_verification_email",
            new=AsyncMock(),
        ),
    ):
        resp = TestClient(app, raise_server_exceptions=True).post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",
                "display_name": "Test User",
            },
        )
    assert resp.status_code == 201


def test_register_duplicate_email():
    with patch(
        "app.api.v1.endpoints.auth_register.create_keycloak_user",
        new=AsyncMock(
            side_effect=ValueError("An account with this email already exists.")
        ),
    ):
        resp = TestClient(app, raise_server_exceptions=True).post(
            "/api/v1/auth/register",
            json={
                "email": "existing@example.com",
                "password": "password123",
                "display_name": "Test",
            },
        )
    assert resp.status_code == 409


def test_register_short_password():
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "short", "display_name": "Test"},
    )
    assert resp.status_code == 422  # validation error


def test_register_keycloak_unavailable():
    with patch(
        "app.api.v1.endpoints.auth_register.create_keycloak_user",
        new=AsyncMock(side_effect=RuntimeError("connection refused")),
    ):
        resp = TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",
                "display_name": "Test",
            },
        )
    assert resp.status_code == 502


def test_register_empty_display_name():
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "password123", "display_name": "   "},
    )
    assert resp.status_code == 422
