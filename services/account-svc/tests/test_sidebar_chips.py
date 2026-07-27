"""Tests for the sidebar_chips field on /api/v1/user/ui-settings (2026-07-22).

The chip row replaced the USE_CASE_TABS category tabs in the tool panel.
Same mocked-session style as test_tool_groups.py: fake auth via dependency
override, AsyncMock DB.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


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


def _fake_row(sidebar_chips=None):
    row = MagicMock()
    row.tool_view = "grid"
    row.keybindings = {}
    row.panel_sizes = {}
    row.onboarding_seen = False
    row.sidebar_chips = sidebar_chips if sidebar_chips is not None else []
    return row


CHIPS = [
    {"type": "view", "id": "all"},
    {"type": "view", "id": "pinned"},
    {"type": "group", "id": "hashing"},
    {"type": "custom_group", "id": str(uuid.uuid4())},
]


@pytest.mark.asyncio
async def test_get_defaults_to_empty_when_no_row(async_client, app):
    """GET /ui-settings with no settings row returns sidebar_chips=[]."""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)
    _override_deps(app, mock_db)
    try:
        response = await async_client.get("/api/v1/user/ui-settings")
        assert response.status_code == 200
        assert response.json()["sidebar_chips"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sidebar_chips_round_trip(async_client, app):
    """PUT persists the ordered chip list and echoes it back; GET returns it."""
    row = _fake_row()
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=row)
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/ui-settings", json={"sidebar_chips": CHIPS}
        )
        assert response.status_code == 200
        assert row.sidebar_chips == CHIPS  # order preserved
        assert response.json()["sidebar_chips"] == CHIPS
        mock_db.commit.assert_awaited()

        get_response = await async_client.get("/api/v1/user/ui-settings")
        assert get_response.status_code == 200
        assert get_response.json()["sidebar_chips"] == CHIPS
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_partial_update_leaves_chips_untouched(async_client, app):
    """PUT without sidebar_chips must not clobber the stored list."""
    row = _fake_row(sidebar_chips=list(CHIPS))
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=row)
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/ui-settings", json={"tool_view": "list"}
        )
        assert response.status_code == 200
        assert row.sidebar_chips == CHIPS
        assert response.json()["sidebar_chips"] == CHIPS
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_duplicate_chips_are_deduped(async_client, app):
    """PUT with duplicate (type, id) pairs stores an order-preserving dedupe."""
    row = _fake_row()
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=row)
    _override_deps(app, mock_db)
    try:
        doubled = CHIPS + [CHIPS[0], CHIPS[2]]
        response = await async_client.put(
            "/api/v1/user/ui-settings", json={"sidebar_chips": doubled}
        )
        assert response.status_code == 200
        assert response.json()["sidebar_chips"] == CHIPS
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_chips",
    [
        [{"type": "persona", "id": "writer"}],  # unknown type
        [{"type": "view"}],  # missing id
        [{"type": "view", "id": ""}],  # empty id
        [{"type": "group", "id": "x" * 101}],  # id too long
        [{"type": "view", "id": f"v{i}"} for i in range(41)],  # over the 40 cap
    ],
)
async def test_invalid_chips_rejected(async_client, app, bad_chips):
    """Structurally invalid chip lists are rejected with 422."""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=_fake_row())
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/ui-settings", json={"sidebar_chips": bad_chips}
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
