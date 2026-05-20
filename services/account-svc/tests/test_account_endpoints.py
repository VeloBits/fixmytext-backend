"""
Account service endpoint tests.

Tests:
1. GET /health → 200
2. GET /api/v1/user/preferences no JWT → 401
3. GET /api/v1/history no JWT → 401
4. GET /api/v1/share/{id} with mocked DB returning None → 404
5. POST /api/v1/history with mocked auth + DB → 201
6. GET /api/v1/user/ui-settings no JWT → 401
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_health_returns_200(async_client):
    """GET /health should return 200 with service info."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "account-svc"


@pytest.mark.asyncio
async def test_preferences_requires_auth(async_client):
    """GET /api/v1/user/preferences without a JWT should return 401."""
    response = await async_client.get("/api/v1/user/preferences")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_history_list_requires_auth(async_client):
    """GET /api/v1/history without a JWT should return 401."""
    response = await async_client.get("/api/v1/history")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_share_not_found(async_client):
    """GET /api/v1/share/{id} with a valid UUID that doesn't exist in DB → 404."""
    share_id = str(uuid.uuid4())

    # Mock the DB session so scalar_one_or_none returns None (share not found)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    from app.db.session import get_db
    from main import app

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = await async_client.get(f"/api/v1/share/{share_id}")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_history_post_with_mocked_auth_and_db(async_client):
    """POST /api/v1/history with mocked auth + DB should return 201."""
    import uuid as _uuid
    from datetime import UTC, datetime

    from app.core.deps import get_current_user
    from app.db.session import get_db
    from main import app

    fake_user_id = _uuid.uuid4()

    # Create a minimal fake user
    fake_user = MagicMock()
    fake_user.id = fake_user_id

    # Create a fake OperationHistory row that matches the response schema
    fake_row = MagicMock()
    fake_row.id = _uuid.uuid4()
    fake_row.tool_id = "word-counter"
    fake_row.tool_label = "Word Counter"
    fake_row.tool_type = "local"
    fake_row.input_preview = "Hello world"
    fake_row.output_preview = "2 words"
    fake_row.input_length = 11
    fake_row.output_length = 7
    fake_row.status = "success"
    fake_row.created_at = datetime.now(UTC)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    # After refresh, the mock_db.refresh call populates the row — simulate by
    # making refresh a no-op (the fake_row already has all fields set)
    async def fake_refresh(obj):
        pass

    mock_db.refresh.side_effect = fake_refresh

    # Patch OperationHistory constructor to return our fake_row
    with patch("app.api.v1.endpoints.history.OperationHistory", return_value=fake_row):

        async def override_get_current_user():
            return fake_user

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.post(
                "/api/v1/history",
                json={
                    "tool_id": "word-counter",
                    "tool_label": "Word Counter",
                    "tool_type": "local",
                    "input_preview": "Hello world",
                    "output_preview": "2 words",
                    "input_length": 11,
                    "output_length": 7,
                    "status": "success",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["tool_id"] == "word-counter"
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ui_settings_requires_auth(async_client):
    """GET /api/v1/user/ui-settings without a JWT should return 401."""
    response = await async_client.get("/api/v1/user/ui-settings")
    assert response.status_code == 401
