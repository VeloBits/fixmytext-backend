"""Auth path tests for ai-svc endpoints not covered by test_ai_endpoints.py.

Covers:
- GET /ai/jobs/{job_id} ownership check (job owned by another user → 403)
- GET /ai/jobs/{job_id} non-existent job → not_found
- POST /ai/{tool_id}/stream auth gate
- No Bearer on job status → 401
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from app.api.v1.endpoints.ai import AuthenticatedUser


def _make_verified_user(user_id: str = "user-abc") -> AuthenticatedUser:
    from app.api.v1.endpoints.ai import AuthenticatedUser

    return AuthenticatedUser(
        id=user_id,
        email="test@example.com",
        is_email_verified=True,
    )


# ── GET /ai/jobs/{job_id} ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_status_no_token_returns_401(client):
    """GET /jobs/{id} without Authorization → 401."""
    response = await client.get("/api/v1/ai/jobs/some-job-id")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_job_status_wrong_owner_returns_403(client):
    """GET /jobs/{id} — job owned by a different user → 403 (IDOR fix H3)."""
    from app.api.v1.endpoints.ai import get_current_user
    from main import app

    requesting_user = _make_verified_user("user-requester")
    job_owner_id = "user-different-owner"

    mock_info = MagicMock()
    mock_info.args = ["summarize", "some text", job_owner_id, {}]
    mock_info.start_ms = None
    mock_info.finish_ms = None

    mock_job = AsyncMock()
    mock_job.info = AsyncMock(return_value=mock_info)

    mock_pool = AsyncMock()
    mock_pool.job = AsyncMock(return_value=mock_job)

    app.dependency_overrides[get_current_user] = lambda: requesting_user
    try:
        with patch(
            "app.api.v1.endpoints.ai._get_arq_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            response = await client.get(
                "/api/v1/ai/jobs/test-job-123",
                headers={"Authorization": "Bearer valid.token"},
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_job_status_correct_owner_returns_status(client):
    """GET /jobs/{id} — job owned by the requesting user → 200 with status."""
    from app.api.v1.endpoints.ai import get_current_user
    from main import app

    user_id = "user-owner"
    requesting_user = _make_verified_user(user_id)

    mock_info = MagicMock()
    mock_info.args = ["summarize", "some text", user_id, {}]
    mock_info.start_ms = None
    mock_info.finish_ms = None
    mock_info.success = None

    mock_job = AsyncMock()
    mock_job.info = AsyncMock(return_value=mock_info)
    # result() raises (job not done yet)
    mock_job.result = AsyncMock(side_effect=Exception("not ready"))

    mock_pool = AsyncMock()
    mock_pool.job = AsyncMock(return_value=mock_job)

    app.dependency_overrides[get_current_user] = lambda: requesting_user
    try:
        with patch(
            "app.api.v1.endpoints.ai._get_arq_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            response = await client.get(
                "/api/v1/ai/jobs/test-job-123",
                headers={"Authorization": "Bearer valid.token"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == "test-job-123"
        assert body["status"] in (
            "queued",
            "in_progress",
            "complete",
            "failed",
            "not_found",
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_job_status_nonexistent_job_returns_not_found(client):
    """GET /jobs/{id} where pool.job() returns None → status=not_found."""
    from app.api.v1.endpoints.ai import get_current_user
    from main import app

    requesting_user = _make_verified_user()

    mock_pool = AsyncMock()
    mock_pool.job = AsyncMock(return_value=None)

    app.dependency_overrides[get_current_user] = lambda: requesting_user
    try:
        with patch(
            "app.api.v1.endpoints.ai._get_arq_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            response = await client.get(
                "/api/v1/ai/jobs/no-such-job",
                headers={"Authorization": "Bearer valid.token"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "not_found"
    finally:
        app.dependency_overrides.clear()


# ── POST /ai/{tool_id}/stream ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_no_token_returns_401(client):
    """POST /ai/{tool_id}/stream without Authorization → 401."""
    response = await client.post(
        "/api/v1/ai/summarize/stream",
        json={"text": "hello"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_stream_unverified_email_returns_403(client):
    """POST /ai/{tool_id}/stream with unverified email → 403."""
    from app.api.v1.endpoints.ai import AuthenticatedUser, get_current_user
    from main import app

    unverified = AuthenticatedUser(
        id="uid", email="u@test.com", is_email_verified=False
    )
    app.dependency_overrides[get_current_user] = lambda: unverified
    try:
        response = await client.post(
            "/api/v1/ai/summarize/stream",
            headers={"Authorization": "Bearer x"},
            json={"text": "hello"},
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "email_not_verified"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_stream_unknown_tool_returns_404(client):
    """POST /ai/{nonexistent}/stream with valid auth → 404."""
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    verified = _make_verified_user()
    app.dependency_overrides[get_verified_user] = lambda: verified
    try:
        response = await client.post(
            "/api/v1/ai/totally-fake-tool/stream",
            headers={"Authorization": "Bearer x"},
            json={"text": "hello"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
