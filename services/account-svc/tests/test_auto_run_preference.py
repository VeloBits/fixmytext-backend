"""Tests for the auto_run field on /api/v1/user/preferences (2026-08-03).

Manual "Run" became the default tool-execution mode; auto_run is the opt-in
that restores debounce-driven execution. Same mocked-session style as
test_sidebar_chips.py: fake auth via dependency override, AsyncMock DB.
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


def _fake_row(auto_run=False, theme="dark"):
    row = MagicMock()
    row.theme = theme
    row.persona = None
    row.theme_skin = None
    row.auto_run = auto_run
    return row


@pytest.mark.asyncio
async def test_get_defaults_to_false_when_no_row(async_client, app):
    """GET /preferences with no preferences row returns auto_run=False.

    Manual Run is the safe default - a user who never toggled it must not
    inherit the old quota-burning debounce behavior.
    """
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)
    _override_deps(app, mock_db)
    try:
        response = await async_client.get("/api/v1/user/preferences")
        assert response.status_code == 200
        assert response.json()["auto_run"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_returns_stored_auto_run(async_client, app):
    """GET /preferences echoes the persisted opt-in."""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=_fake_row(auto_run=True))
    _override_deps(app, mock_db)
    try:
        response = await async_client.get("/api/v1/user/preferences")
        assert response.status_code == 200
        assert response.json()["auto_run"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, False])
async def test_auto_run_round_trip(async_client, app, value):
    """PUT persists auto_run and echoes it back."""
    row = _fake_row(auto_run=not value)
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=row)
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/preferences", json={"auto_run": value}
        )
        assert response.status_code == 200
        assert row.auto_run is value
        assert response.json()["auto_run"] is value
        mock_db.commit.assert_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_partial_update_leaves_auto_run_untouched(async_client, app):
    """PUT without auto_run must not clobber the stored opt-in."""
    row = _fake_row(auto_run=True)
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=row)
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/preferences", json={"theme": "light"}
        )
        assert response.status_code == 200
        assert row.auto_run is True
        assert response.json()["auto_run"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_setting_auto_run_leaves_theme_untouched(async_client, app):
    """Toggling auto_run must not reset the user's theme."""
    row = _fake_row(auto_run=False, theme="light")
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=row)
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/preferences", json={"auto_run": True}
        )
        assert response.status_code == 200
        assert row.theme == "light"
        assert response.json()["theme"] == "light"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_value", ["maybe", 2, [], {}])
async def test_invalid_auto_run_rejected(async_client, app, bad_value):
    """Non-boolean auto_run values are rejected with 422.

    Note pydantic's lax mode intentionally coerces bool-ish strings
    ("yes"/"true"/"on") - only genuinely non-boolean input 422s. The client
    only ever sends real booleans, so lax coercion is not a concern here.
    """
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=_fake_row())
    _override_deps(app, mock_db)
    try:
        response = await async_client.put(
            "/api/v1/user/preferences", json={"auto_run": bad_value}
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
