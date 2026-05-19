"""Tests for /api/v1/user/* endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_prefs(**kwargs):
    from app.db.models.preferences import UserPreferences

    prefs = UserPreferences(
        user_id=kwargs.get("user_id", uuid.uuid4()),
    )
    prefs.theme = kwargs.get("theme", "dark")
    prefs.persona = kwargs.get("persona", "developer")
    prefs.theme_skin = kwargs.get("theme_skin", "default")
    return prefs


def make_template(**kwargs):
    from app.db.models.template import UserTemplate

    tmpl = UserTemplate(
        user_id=kwargs.get("user_id", uuid.uuid4()),
        name=kwargs.get("name", "My Template"),
        text=kwargs.get("text", "Template text"),
        tool_id=kwargs.get("tool_id", "uppercase"),
    )
    tmpl.id = kwargs.get("id", uuid.uuid4())
    tmpl.is_deleted = kwargs.get("is_deleted", False)
    tmpl.created_at = kwargs.get("created_at", datetime.now(UTC))
    tmpl.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    return tmpl


def make_gamification(**kwargs):
    from app.db.models.gamification import UserGamification

    gam = UserGamification(
        user_id=kwargs.get("user_id", uuid.uuid4()),
    )
    gam.xp = kwargs.get("xp", 100)
    gam.streak_current = kwargs.get("streak_current", 3)
    gam.streak_last_date = kwargs.get("streak_last_date")
    gam.total_ops = kwargs.get("total_ops", 10)
    gam.total_chars = kwargs.get("total_chars", 500)
    gam.achievements = kwargs.get("achievements", ["first_step"])
    gam.completed_quests = kwargs.get("completed_quests", [])
    gam.daily_quest_id = kwargs.get("daily_quest_id")
    gam.daily_quest_date = kwargs.get("daily_quest_date")
    gam.daily_quest_completed = kwargs.get("daily_quest_completed", False)
    gam.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    return gam


def make_ui_settings(**kwargs):
    from app.db.models.user_ui_settings import UserUiSettings

    s = UserUiSettings(
        user_id=kwargs.get("user_id", uuid.uuid4()),
    )
    s.tool_view = kwargs.get("tool_view", "grid")
    s.keybindings = kwargs.get("keybindings", {})
    s.panel_sizes = kwargs.get("panel_sizes", {})
    return s


# ── GET /user/preferences ─────────────────────────────────────────────────────


def test_get_preferences_no_record(client, mock_db):
    mock_db.get.return_value = None
    resp = client.get("/api/v1/user/preferences")
    assert resp.status_code == 200
    data = resp.json()
    assert "theme" in data


def test_get_preferences_existing(client, mock_db, fake_user):
    prefs = make_prefs(user_id=fake_user.id, theme="dark", persona="developer")
    mock_db.get.return_value = prefs
    resp = client.get("/api/v1/user/preferences")
    assert resp.status_code == 200
    data = resp.json()
    assert data["theme"] == "dark"
    assert data["persona"] == "developer"


def test_get_preferences_requires_auth(unauth_client):
    resp = unauth_client.get("/api/v1/user/preferences")
    assert resp.status_code == 401


# ── PUT /user/preferences ─────────────────────────────────────────────────────


def test_update_preferences_creates_new(client, mock_db, fake_user):
    mock_db.get.return_value = None  # no existing prefs

    async def _refresh(obj):
        obj.theme = "light"
        obj.persona = "writer"
        obj.theme_skin = "default"

    mock_db.refresh.side_effect = _refresh

    resp = client.put(
        "/api/v1/user/preferences",
        json={"theme": "light", "persona": "writer"},
    )
    assert resp.status_code == 200
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited()


def test_update_preferences_updates_existing(client, mock_db, fake_user):
    prefs = make_prefs(user_id=fake_user.id, theme="dark")
    mock_db.get.return_value = prefs

    async def _refresh(obj):
        obj.theme = "light"
        obj.persona = "developer"
        obj.theme_skin = "default"

    mock_db.refresh.side_effect = _refresh

    resp = client.put(
        "/api/v1/user/preferences",
        json={"theme": "light"},
    )
    assert resp.status_code == 200


def test_update_preferences_requires_auth(unauth_client):
    resp = unauth_client.put("/api/v1/user/preferences", json={"theme": "dark"})
    assert resp.status_code == 401


# ── GET /user/gamification ────────────────────────────────────────────────────


def test_get_gamification_no_record(client, mock_db):
    mock_db.get.return_value = None

    # Mock the execute calls for favorites and discovered tools
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    resp = client.get("/api/v1/user/gamification")
    assert resp.status_code == 200
    data = resp.json()
    assert "xp" in data


def test_get_gamification_with_data(client, mock_db, fake_user):
    gam = make_gamification(user_id=fake_user.id, xp=250, streak_current=5)
    mock_db.get.return_value = gam

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    resp = client.get("/api/v1/user/gamification")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xp"] == 250
    assert data["streak_current"] == 5


def test_get_gamification_requires_auth(unauth_client):
    resp = unauth_client.get("/api/v1/user/gamification")
    assert resp.status_code == 401


# ── PUT /user/gamification ────────────────────────────────────────────────────


def test_update_gamification_creates_new(client, mock_db, fake_user):
    mock_db.get.return_value = None

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    async def _refresh(obj):
        obj.xp = 10
        obj.streak_current = 1
        obj.streak_last_date = None
        obj.total_ops = 1
        obj.total_chars = 5
        obj.achievements = []
        obj.completed_quests = []
        obj.daily_quest_id = None
        obj.daily_quest_date = None
        obj.daily_quest_completed = False
        obj.updated_at = datetime.now(UTC)

    mock_db.refresh.side_effect = _refresh

    resp = client.put(
        "/api/v1/user/gamification",
        json={"xp": 10, "streak_current": 1, "total_ops": 1, "total_chars": 5},
    )
    assert resp.status_code == 200
    mock_db.add.assert_called_once()


def test_update_gamification_requires_auth(unauth_client):
    resp = unauth_client.put("/api/v1/user/gamification", json={"xp": 10})
    assert resp.status_code == 401


# ── Templates CRUD ────────────────────────────────────────────────────────────


def test_list_templates_empty(client, mock_db):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    resp = client.get("/api/v1/user/templates")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_templates_with_data(client, mock_db, fake_user):
    tmpl = make_template(user_id=fake_user.id, name="Test Template")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [tmpl]
    mock_db.execute.return_value = result

    resp = client.get("/api/v1/user/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Template"


def test_create_template_success(client, mock_db):
    resp = client.post(
        "/api/v1/user/templates",
        json={"name": "My Template", "text": "Some text", "tool_id": "uppercase"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Template"


def test_create_template_missing_name(client):
    resp = client.post(
        "/api/v1/user/templates",
        json={"text": "Some text"},
    )
    assert resp.status_code == 422


def test_update_template_not_found(client, mock_db):
    mock_db.get.return_value = None  # update uses db.get()
    resp = client.put(
        f"/api/v1/user/templates/{uuid.uuid4()}",
        json={"name": "Updated"},
    )
    assert resp.status_code == 404


def test_update_template_success(client, mock_db, fake_user):
    tmpl_id = uuid.uuid4()
    tmpl = make_template(id=tmpl_id, user_id=fake_user.id)
    mock_db.get.return_value = tmpl  # update uses db.get()

    async def _refresh(obj):
        obj.id = tmpl_id
        obj.name = "Updated"
        obj.text = tmpl.text
        obj.tool_id = tmpl.tool_id
        obj.created_at = tmpl.created_at
        obj.updated_at = datetime.now(UTC)

    mock_db.refresh.side_effect = _refresh

    resp = client.put(
        f"/api/v1/user/templates/{tmpl_id}",
        json={"name": "Updated"},
    )
    assert resp.status_code == 200


def test_delete_template_not_found(client, mock_db):
    mock_db.get.return_value = None  # delete uses db.get()
    resp = client.delete(f"/api/v1/user/templates/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_template_success(client, mock_db, fake_user):
    tmpl_id = uuid.uuid4()
    tmpl = make_template(id=tmpl_id, user_id=fake_user.id)
    mock_db.get.return_value = tmpl  # delete uses db.get()

    resp = client.delete(f"/api/v1/user/templates/{tmpl_id}")
    assert resp.status_code == 204


def test_templates_require_auth(unauth_client):
    resp = unauth_client.get("/api/v1/user/templates")
    assert resp.status_code == 401


# ── UI Settings ───────────────────────────────────────────────────────────────


def test_get_ui_settings_no_record(client, mock_db):
    mock_db.get.return_value = None
    resp = client.get("/api/v1/user/ui-settings")
    assert resp.status_code == 200


def test_get_ui_settings_existing(client, mock_db, fake_user):
    s = make_ui_settings(user_id=fake_user.id, tool_view="list")
    mock_db.get.return_value = s
    resp = client.get("/api/v1/user/ui-settings")
    assert resp.status_code == 200
    assert resp.json()["tool_view"] == "list"


def test_update_ui_settings(client, mock_db, fake_user):
    mock_db.get.return_value = None

    async def _refresh(obj):
        obj.tool_view = "list"
        obj.keybindings = {}
        obj.panel_sizes = {}

    mock_db.refresh.side_effect = _refresh

    resp = client.put("/api/v1/user/ui-settings", json={"tool_view": "list"})
    assert resp.status_code == 200


# ── Favorites ─────────────────────────────────────────────────────────────────


def test_get_favorites_empty(client, mock_db):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    resp = client.get("/api/v1/user/favorites")
    assert resp.status_code == 200
    assert resp.json()["favorites"] == []


def test_add_favorite(client, mock_db):
    resp = client.post("/api/v1/user/favorites/uppercase")
    assert resp.status_code in (200, 201, 204)


def test_remove_favorite(client, mock_db):
    resp = client.delete("/api/v1/user/favorites/uppercase")
    assert resp.status_code in (200, 204)


# ── Tool stats ────────────────────────────────────────────────────────────────


def test_get_tool_stats_empty(client, mock_db):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    resp = client.get("/api/v1/user/tool-stats")
    assert resp.status_code == 200
    assert resp.json()["stats"] == []
