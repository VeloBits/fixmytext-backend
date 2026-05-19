"""Extended tests for /api/v1/user/* endpoints — pipelines, discovered tools, spin history."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

# ── Pipelines ────────────────────────────────────────────────────────────────


def test_list_pipelines_empty(client, mock_db):
    """Empty pipeline list returns empty array."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    resp = client.get("/api/v1/user/pipelines")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_pipeline_success(client, mock_db, fake_user):
    """Creating a pipeline returns 201."""
    from app.db.models.user_pipeline import UserPipeline, UserPipelineStep

    pipeline = UserPipeline(
        user_id=fake_user.id,
        name="My Pipeline",
        description="Test",
    )
    pipeline.id = uuid.uuid4()
    pipeline.is_active = True
    pipeline.created_at = datetime.now(UTC)
    pipeline.updated_at = datetime.now(UTC)

    step = UserPipelineStep(
        pipeline_id=pipeline.id,
        step_order=1,
        tool_id="uppercase",
        tool_label="Uppercase",
        config=None,
    )
    step.id = uuid.uuid4()
    pipeline.steps = [step]

    # mock the final select after commit
    select_result = MagicMock()
    select_result.scalar_one.return_value = pipeline
    mock_db.execute.return_value = select_result

    resp = client.post(
        "/api/v1/user/pipelines",
        json={
            "name": "My Pipeline",
            "description": "Test",
            "steps": [
                {"step_order": 1, "tool_id": "uppercase", "tool_label": "Uppercase"},
            ],
        },
    )
    assert resp.status_code == 201


def test_create_pipeline_missing_name(client):
    """Pipeline without name returns 422."""
    resp = client.post(
        "/api/v1/user/pipelines",
        json={"description": "No name"},
    )
    assert resp.status_code == 422


def test_delete_pipeline_not_found(client, mock_db):
    """Deleting nonexistent pipeline returns 404."""
    mock_db.get.return_value = None
    resp = client.delete(f"/api/v1/user/pipelines/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_pipeline_success(client, mock_db, fake_user):
    """Deleting an owned pipeline returns 204."""
    from app.db.models.user_pipeline import UserPipeline

    pipeline = UserPipeline(user_id=fake_user.id, name="Test")
    pipeline.id = uuid.uuid4()
    pipeline.is_active = True
    mock_db.get.return_value = pipeline

    resp = client.delete(f"/api/v1/user/pipelines/{pipeline.id}")
    assert resp.status_code == 204


def test_delete_pipeline_wrong_user(client, mock_db):
    """Deleting another user's pipeline returns 404."""
    from app.db.models.user_pipeline import UserPipeline

    pipeline = UserPipeline(user_id=uuid.uuid4(), name="Other")
    pipeline.id = uuid.uuid4()
    pipeline.is_active = True
    mock_db.get.return_value = pipeline

    resp = client.delete(f"/api/v1/user/pipelines/{pipeline.id}")
    assert resp.status_code == 404


def test_pipelines_require_auth(unauth_client):
    """Pipeline list requires authentication."""
    resp = unauth_client.get("/api/v1/user/pipelines")
    assert resp.status_code == 401


# ── Discovered Tools ─────────────────────────────────────────────────────────


def test_get_discovered_tools_empty(client, mock_db):
    """Empty discovered tools list returns 0 count."""
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = []

    call_count = 0

    async def execute_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return count_result
        return list_result

    mock_db.execute.side_effect = execute_side_effect

    resp = client.get("/api/v1/user/discovered-tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["tools"] == []


def test_discovered_tools_require_auth(unauth_client):
    """Discovered tools requires authentication."""
    resp = unauth_client.get("/api/v1/user/discovered-tools")
    assert resp.status_code == 401


# ── Spin History ─────────────────────────────────────────────────────────────


def test_get_spin_history_empty(client, mock_db):
    """Empty spin history returns empty list."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    resp = client.get("/api/v1/user/spin-history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["spins"] == []


def test_spin_history_requires_auth(unauth_client):
    """Spin history requires authentication."""
    resp = unauth_client.get("/api/v1/user/spin-history")
    assert resp.status_code == 401


# ── UI Settings ──────────────────────────────────────────────────────────────


def test_update_ui_settings_creates_new(client, mock_db):
    """Creating new UI settings when none exist."""
    mock_db.get.return_value = None

    async def _refresh(obj):
        obj.tool_view = "list"
        obj.keybindings = {"save": "ctrl+s"}
        obj.panel_sizes = {"left": 300}

    mock_db.refresh.side_effect = _refresh

    resp = client.put(
        "/api/v1/user/ui-settings",
        json={"tool_view": "list", "keybindings": {"save": "ctrl+s"}},
    )
    assert resp.status_code == 200


def test_ui_settings_require_auth(unauth_client):
    """UI settings require authentication."""
    resp = unauth_client.get("/api/v1/user/ui-settings")
    assert resp.status_code == 401


# ── Tool Stats ───────────────────────────────────────────────────────────────


def test_tool_stats_require_auth(unauth_client):
    """Tool stats require authentication."""
    resp = unauth_client.get("/api/v1/user/tool-stats")
    assert resp.status_code == 401


# ── Favorites ────────────────────────────────────────────────────────────────


def test_add_favorite_existing_idempotent(client, mock_db, fake_user):
    """Adding an already-favorited tool returns it without error."""
    from app.db.models.user_favorite_tool import UserFavoriteTool

    fav = UserFavoriteTool(user_id=fake_user.id, tool_id="uppercase", sort_order=0)
    mock_db.get.return_value = fav

    resp = client.post("/api/v1/user/favorites/uppercase")
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["tool_id"] == "uppercase"


def test_remove_favorite_nonexistent(client, mock_db):
    """Removing a non-favorited tool returns 204 (no-op)."""
    mock_db.get.return_value = None
    resp = client.delete("/api/v1/user/favorites/nonexistent")
    assert resp.status_code == 204


def test_favorites_require_auth(unauth_client):
    """Favorites require authentication."""
    resp = unauth_client.get("/api/v1/user/favorites")
    assert resp.status_code == 401
