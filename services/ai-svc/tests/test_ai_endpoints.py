"""
Tests for ai-svc AI endpoints.

Uses httpx.AsyncClient against the FastAPI app directly (no real server).
Mocks ``ai_service.run_ai_tool`` to avoid Groq API calls.
JWT verification is mocked to avoid needing a real Keycloak instance.
"""

from unittest.mock import AsyncMock, patch

import pytest

# ── Health ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_200(client):
    """GET /health must return 200 with status=ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ai-svc"


# ── Auth ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_token_returns_401(client):
    """POST without Authorization header must return 401."""
    response = await client.post(
        "/api/v1/ai/generate-hashtags",
        json={"text": "hello world"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client):
    """POST with a malformed JWT must return 401."""
    response = await client.post(
        "/api/v1/ai/generate-hashtags",
        headers={"Authorization": "Bearer this.is.invalid"},
        json={"text": "hello world"},
    )
    assert response.status_code == 401


# ── Tool dispatch ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_tool_returns_404(client):
    """POST to a nonexistent tool_id must return 404 after valid auth."""
    from app.api.v1.endpoints.ai import AuthenticatedUser, get_verified_user
    from main import app

    verified_user = AuthenticatedUser(
        id="test-user-id",
        email="test@example.com",
        is_email_verified=True,
    )

    app.dependency_overrides[get_verified_user] = lambda: verified_user
    try:
        response = await client.post(
            "/api/v1/ai/nonexistent-tool",
            json={"text": "hello world"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generate_hashtags_returns_200(client):
    """POST /api/v1/ai/generate-hashtags with mocked auth + ai_service returns 200."""
    from app.api.v1.endpoints.ai import AuthenticatedUser, get_verified_user
    from main import app

    verified_user = AuthenticatedUser(
        id="test-user-id",
        email="test@example.com",
        is_email_verified=True,
    )

    app.dependency_overrides[get_verified_user] = lambda: verified_user

    with (
        patch(
            "app.api.v1.endpoints.ai.check_entitlement",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.ai_service.run_ai_tool",
            new=AsyncMock(return_value="#Python #FastAPI #Testing"),
        ),
    ):
        try:
            response = await client.post(
                "/api/v1/ai/generate-hashtags",
                json={"text": "Building a FastAPI service with Python"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["operation"] == "generate-hashtags"
            assert body["original"] == "Building a FastAPI service with Python"
            assert "#Python" in body["result"]
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_unverified_email_returns_403(client):
    """POST with valid token but unverified email must return 403."""
    from app.api.v1.endpoints.ai import AuthenticatedUser, get_current_user
    from main import app

    unverified_user = AuthenticatedUser(
        id="test-user-id",
        email="test@example.com",
        is_email_verified=False,
    )

    app.dependency_overrides[get_current_user] = lambda: unverified_user
    try:
        response = await client.post(
            "/api/v1/ai/generate-hashtags",
            headers={"Authorization": "Bearer fake-token"},
            json={"text": "hello"},
        )
        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["code"] == "email_not_verified"
    finally:
        app.dependency_overrides.clear()
