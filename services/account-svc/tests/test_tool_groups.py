"""Tests for the tool-groups endpoints (custom tool groups feature, 2026-07-14).

Same mocked-session style as test_account_endpoints.py: fake auth via
dependency override, AsyncMock DB with per-call result side effects.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

GROUP_ID = uuid.uuid4()


def _override_deps(app, mock_db):
    """Install fake auth + DB overrides; returns the fake user."""
    from app.core.deps import get_current_user
    from app.db.session import get_db

    fake_user = MagicMock()
    fake_user.id = uuid.uuid4()
    fake_user.keycloak_id = uuid.uuid4()

    async def override_get_current_user():
        return fake_user

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    return fake_user


def _fake_group(name="Writing essentials", tool_ids=("fix_grammar", "paraphrase")):
    group = MagicMock()
    group.id = GROUP_ID
    group.name = name
    group.sort_order = 0
    group.created_at = datetime.now(UTC)
    group.updated_at = datetime.now(UTC)
    group.items = []
    for i, tool_id in enumerate(tool_ids):
        item = MagicMock()
        item.tool_id = tool_id
        item.sort_order = i
        group.items.append(item)
    return group


def _result(scalar_one_or_none=None, scalar=None, all_rows=None, scalar_one=None):
    """Build a fake SQLAlchemy result for one db.execute call."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalar_one.return_value = scalar_one
    result.scalars.return_value.all.return_value = all_rows or []
    return result


# ── Auth ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", "/api/v1/user/tool-groups"),
        ("POST", "/api/v1/user/tool-groups"),
        ("PUT", f"/api/v1/user/tool-groups/{GROUP_ID}"),
        ("DELETE", f"/api/v1/user/tool-groups/{GROUP_ID}"),
        ("POST", f"/api/v1/user/tool-groups/{GROUP_ID}/tools/fix_grammar"),
        ("DELETE", f"/api/v1/user/tool-groups/{GROUP_ID}/tools/fix_grammar"),
    ],
)
async def test_tool_groups_require_auth(async_client, method, url):
    """Every tool-groups route must reject unauthenticated requests."""
    response = await async_client.request(
        method, url, json={"name": "x"} if method in ("POST", "PUT") else None
    )
    assert response.status_code == 401


# ── List ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tool_groups_returns_groups_in_order(async_client, app):
    """GET /tool-groups returns the user's groups with their tools."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_result(all_rows=[_fake_group()]))
    _override_deps(app, mock_db)
    try:
        response = await async_client.get("/api/v1/user/tool-groups")
        assert response.status_code == 200
        data = response.json()
        assert len(data["groups"]) == 1
        group = data["groups"][0]
        assert group["name"] == "Writing essentials"
        assert [t["tool_id"] for t in group["tools"]] == ["fix_grammar", "paraphrase"]
    finally:
        app.dependency_overrides.clear()


# ── Create ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_tool_group_happy_path(async_client, app):
    """POST /tool-groups creates a group with deduped, ordered tools (201)."""
    created = _fake_group(name="My kit", tool_ids=("summarize", "eli5"))
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _result(scalar_one_or_none=None),  # no same-name group
            _result(scalar=0),  # group count under limit
            _result(scalar=None),  # no existing sort_order
            _result(scalar_one=created),  # re-select after commit
        ]
    )
    _override_deps(app, mock_db)
    try:
        response = await async_client.post(
            "/api/v1/user/tool-groups",
            json={"name": "My kit", "tool_ids": ["summarize", "eli5", "summarize"]},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "My kit"
        # group + 2 items (third tool_id is a dupe and must be dropped)
        assert mock_db.add.call_count == 3
        mock_db.commit.assert_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_tool_group_idempotent_by_name(async_client, app):
    """POST with an existing name returns the existing group (200), no writes."""
    existing = _fake_group()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute = AsyncMock(return_value=_result(scalar_one_or_none=existing))
    _override_deps(app, mock_db)
    try:
        response = await async_client.post(
            "/api/v1/user/tool-groups",
            json={"name": "Writing essentials", "tool_ids": ["other_tool"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(GROUP_ID)
        # tool_ids from the request must NOT be merged into the existing group
        assert [t["tool_id"] for t in data["tools"]] == ["fix_grammar", "paraphrase"]
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_tool_group_limit_reached(async_client, app):
    """POST beyond MAX_TOOL_GROUPS_PER_USER returns 400."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _result(scalar_one_or_none=None),  # no same-name group
            _result(scalar=20),  # at the limit
        ]
    )
    _override_deps(app, mock_db)
    try:
        response = await async_client.post(
            "/api/v1/user/tool-groups", json={"name": "One too many"}
        )
        assert response.status_code == 400
        assert "limit" in response.json()["detail"].lower()
        mock_db.add.assert_not_called()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_tool_group_validates_name(async_client, app):
    """POST with an empty or over-long name fails validation (422)."""
    mock_db = AsyncMock()
    _override_deps(app, mock_db)
    try:
        for bad_name in ("", "x" * 101):
            response = await async_client.post(
                "/api/v1/user/tool-groups", json={"name": bad_name}
            )
            assert response.status_code == 422
        mock_db.execute.assert_not_called()
    finally:
        app.dependency_overrides.clear()


# ── Rename ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_tool_group(async_client, app):
    """PUT /tool-groups/{id} renames an owned group."""
    group = _fake_group()
    renamed = _fake_group(name="Blog kit")
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _result(scalar_one_or_none=group),  # ownership load
            _result(scalar_one_or_none=None),  # no name collision
            _result(scalar_one=renamed),  # re-select after commit
        ]
    )
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            f"/api/v1/user/tool-groups/{GROUP_ID}", json={"name": "Blog kit"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Blog kit"
        assert group.name == "Blog kit"
        mock_db.commit.assert_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rename_tool_group_not_found(async_client, app):
    """PUT on a missing / foreign group returns 404."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_result(scalar_one_or_none=None))
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            f"/api/v1/user/tool-groups/{uuid.uuid4()}", json={"name": "New"}
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rename_tool_group_name_collision(async_client, app):
    """PUT to a name the user already uses returns 409."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _result(scalar_one_or_none=_fake_group()),  # ownership load
            _result(scalar_one_or_none=uuid.uuid4()),  # collision found
        ]
    )
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            f"/api/v1/user/tool-groups/{GROUP_ID}", json={"name": "Taken"}
        )
        assert response.status_code == 409
        mock_db.commit.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


# ── Delete ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_tool_group(async_client, app):
    """DELETE /tool-groups/{id} removes an owned group (204)."""
    group = _fake_group()
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_result(scalar_one_or_none=group))
    _override_deps(app, mock_db)
    try:
        response = await async_client.delete(f"/api/v1/user/tool-groups/{GROUP_ID}")
        assert response.status_code == 204
        mock_db.delete.assert_awaited_once_with(group)
        mock_db.commit.assert_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_tool_group_not_found(async_client, app):
    """DELETE on a missing / foreign group returns 404."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_result(scalar_one_or_none=None))
    _override_deps(app, mock_db)
    try:
        response = await async_client.delete(f"/api/v1/user/tool-groups/{uuid.uuid4()}")
        assert response.status_code == 404
        mock_db.delete.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


# ── Items ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_tool_to_group(async_client, app):
    """POST /tool-groups/{id}/tools/{tool_id} appends with next sort_order (201)."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get = AsyncMock(return_value=None)  # tool not in group yet
    mock_db.execute = AsyncMock(
        side_effect=[
            _result(scalar_one_or_none=_fake_group()),  # ownership load
            _result(scalar=2),  # item count under limit
            _result(scalar=1),  # current max sort_order
        ]
    )
    _override_deps(app, mock_db)
    try:
        response = await async_client.post(
            f"/api/v1/user/tool-groups/{GROUP_ID}/tools/word_count"
        )
        assert response.status_code == 201
        assert response.json() == {"tool_id": "word_count", "sort_order": 2}
        mock_db.add.assert_called_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_tool_to_group_idempotent(async_client, app):
    """POST for a tool already in the group returns 200 with its position."""
    existing_item = MagicMock()
    existing_item.sort_order = 1
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get = AsyncMock(return_value=existing_item)
    mock_db.execute = AsyncMock(return_value=_result(scalar_one_or_none=_fake_group()))
    _override_deps(app, mock_db)
    try:
        response = await async_client.post(
            f"/api/v1/user/tool-groups/{GROUP_ID}/tools/paraphrase"
        )
        assert response.status_code == 200
        assert response.json() == {"tool_id": "paraphrase", "sort_order": 1}
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_tool_to_group_limit_reached(async_client, app):
    """POST beyond MAX_TOOLS_PER_GROUP returns 400."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(
        side_effect=[
            _result(scalar_one_or_none=_fake_group()),  # ownership load
            _result(scalar=50),  # at the limit
        ]
    )
    _override_deps(app, mock_db)
    try:
        response = await async_client.post(
            f"/api/v1/user/tool-groups/{GROUP_ID}/tools/one_more"
        )
        assert response.status_code == 400
        mock_db.add.assert_not_called()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_remove_tool_from_group(async_client, app):
    """DELETE /tool-groups/{id}/tools/{tool_id} removes the item (204)."""
    item = MagicMock()
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=item)
    mock_db.execute = AsyncMock(return_value=_result(scalar_one_or_none=_fake_group()))
    _override_deps(app, mock_db)
    try:
        response = await async_client.delete(
            f"/api/v1/user/tool-groups/{GROUP_ID}/tools/fix_grammar"
        )
        assert response.status_code == 204
        mock_db.delete.assert_awaited_once_with(item)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_remove_tool_from_group_absent_is_silent(async_client, app):
    """DELETE for a tool not in the group still returns 204 (no error)."""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=_result(scalar_one_or_none=_fake_group()))
    _override_deps(app, mock_db)
    try:
        response = await async_client.delete(
            f"/api/v1/user/tool-groups/{GROUP_ID}/tools/not_in_group"
        )
        assert response.status_code == 204
        mock_db.delete.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


# ── Transitional persona / onboarding_seen behavior ──────────────────────────


@pytest.mark.asyncio
async def test_preferences_put_ignores_persona(async_client, app):
    """PUT /preferences from a stale bundle sending persona ignores the field."""
    prefs = MagicMock()
    prefs.theme = "dark"
    prefs.persona = "writer"  # pre-existing DB value, must survive untouched
    prefs.theme_skin = None
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=prefs)
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/preferences",
            json={"theme": "light", "persona": "developer"},
        )
        assert response.status_code == 200
        assert prefs.theme == "light"
        assert prefs.persona == "writer"  # not overwritten
        # response still carries the legacy value for stale readers
        assert response.json()["persona"] == "writer"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ui_settings_onboarding_seen_round_trip(async_client, app):
    """PUT /ui-settings persists onboarding_seen and echoes it back."""
    row = MagicMock()
    row.tool_view = "grid"
    row.keybindings = {}
    row.panel_sizes = {}
    row.onboarding_seen = False
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=row)
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/ui-settings", json={"onboarding_seen": True}
        )
        assert response.status_code == 200
        assert row.onboarding_seen is True
        assert response.json()["onboarding_seen"] is True

        get_response = await async_client.get("/api/v1/user/ui-settings")
        assert get_response.status_code == 200
        assert get_response.json()["onboarding_seen"] is True
    finally:
        app.dependency_overrides.clear()
