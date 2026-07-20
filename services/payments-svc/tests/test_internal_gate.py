"""Full happy-path tests for POST /internal/v1/check-access.

test_internal_auth.py covers the secret guard and the JIT race.
This file covers the endpoint's response shape and principal_type paths
that have no existing test coverage.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_SECRET = "integration-shared-secret"


def _make_user_row(keycloak_id: uuid.UUID) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.keycloak_id = keycloak_id
    u.email = "user@test.com"
    u.is_active = True
    u.is_email_verified = True
    return u


# ── principal_type="user" happy path ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_access_user_allowed_returns_200(async_client, app):
    """POST /internal/v1/check-access with valid secret + existing user → 200 allowed."""
    from app.core.deps import verify_internal_secret
    from app.db.session import get_db

    keycloak_id = uuid.uuid4()
    user = _make_user_row(keycloak_id)
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=user)
    mock_db.commit = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[verify_internal_secret] = lambda: None
    app.dependency_overrides[get_db] = _override_db

    try:
        with patch(
            "app.api.v1.endpoints.internal.check_tool_access",
            new_callable=AsyncMock,
            return_value={
                "allowed": True,
                "reason": "free_use",
                "uses_today": 1,
                "max_free": 3,
                "credits_remaining": 0,
            },
        ):
            response = await async_client.post(
                "/internal/v1/check-access",
                headers={"x-internal-secret": _VALID_SECRET},
                json={
                    "tool_id": "uppercase",
                    "tool_type": "local",
                    "principal_type": "user",
                    "user_id": str(keycloak_id),
                    "email": "user@test.com",
                    "email_verified": True,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is True
    assert data["reason"] == "free_use"
    assert data["uses_today"] == 1
    assert data["max_free"] == 3


@pytest.mark.asyncio
async def test_check_access_user_quota_exhausted_returns_allowed_false(
    async_client, app
):
    """Quota exhausted → 200 with allowed=False (not a 4xx; caller decides UX)."""
    from app.core.deps import verify_internal_secret
    from app.db.session import get_db

    keycloak_id = uuid.uuid4()
    user = _make_user_row(keycloak_id)
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=user)
    mock_db.commit = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[verify_internal_secret] = lambda: None
    app.dependency_overrides[get_db] = _override_db

    try:
        with patch(
            "app.api.v1.endpoints.internal.check_tool_access",
            new_callable=AsyncMock,
            return_value={
                "allowed": False,
                "reason": "quota_exhausted",
                "uses_today": 3,
                "max_free": 3,
                "credits_remaining": 0,
            },
        ):
            response = await async_client.post(
                "/internal/v1/check-access",
                headers={"x-internal-secret": _VALID_SECRET},
                json={
                    "tool_id": "uppercase",
                    "tool_type": "local",
                    "principal_type": "user",
                    "user_id": str(keycloak_id),
                    "email": "user@test.com",
                    "email_verified": True,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is False
    assert data["reason"] == "quota_exhausted"


# ── principal_type="visitor" happy path ──────────────────────────────────────


@pytest.mark.asyncio
async def test_check_access_visitor_allowed_returns_200(async_client, app):
    """POST /internal/v1/check-access visitor type → 200 allowed."""
    from app.core.deps import verify_internal_secret
    from app.db.session import get_db

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[verify_internal_secret] = lambda: None
    app.dependency_overrides[get_db] = _override_db

    try:
        with patch(
            "app.api.v1.endpoints.internal.check_visitor_access",
            new_callable=AsyncMock,
            return_value={
                "allowed": True,
                "reason": "visitor_free",
                "uses_today": 1,
                "max_free": 2,
                "credits_remaining": 0,
            },
        ):
            response = await async_client.post(
                "/internal/v1/check-access",
                headers={"x-internal-secret": _VALID_SECRET},
                json={
                    "tool_id": "uppercase",
                    "tool_type": "local",
                    "principal_type": "visitor",
                    "ip_address": "1.2.3.4",
                    "user_agent": "Mozilla/5.0",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["allowed"] is True


# ── Invalid principal_type → 422 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_access_invalid_principal_type_returns_422(async_client, app):
    """principal_type='robot' → 422 (not a valid value)."""
    from app.core.deps import verify_internal_secret
    from app.db.session import get_db

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[verify_internal_secret] = lambda: None
    app.dependency_overrides[get_db] = _override_db

    try:
        response = await async_client.post(
            "/internal/v1/check-access",
            headers={"x-internal-secret": _VALID_SECRET},
            json={
                "tool_id": "uppercase",
                "tool_type": "local",
                "principal_type": "robot",  # invalid
            },
        )
    finally:
        app.dependency_overrides.clear()

    # Either a Pydantic 422 (if schema validates) or HTTPException 422 from handler
    assert response.status_code in (422, 400)


# ── Missing/wrong secret → 401 (from test_internal_auth.py but kept for completeness) ──


@pytest.mark.asyncio
async def test_check_access_no_secret_returns_401(async_client):
    """POST /internal/v1/check-access with no X-Internal-Secret header → 401."""
    response = await async_client.post(
        "/internal/v1/check-access",
        json={
            "tool_id": "uppercase",
            "tool_type": "local",
            "principal_type": "visitor",
        },
    )
    assert response.status_code == 401


# ── DB error → 503 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_access_db_error_returns_503(async_client, app):
    """SQLAlchemyError from DB during check_access → 503 (fail-closed)."""
    from sqlalchemy.exc import SQLAlchemyError

    from app.core.deps import verify_internal_secret
    from app.db.session import get_db

    keycloak_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)  # user not found
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock(side_effect=SQLAlchemyError("db dead"))
    mock_db.rollback = AsyncMock()
    mock_db.commit = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[verify_internal_secret] = lambda: None
    app.dependency_overrides[get_db] = _override_db

    try:
        response = await async_client.post(
            "/internal/v1/check-access",
            headers={"x-internal-secret": _VALID_SECRET},
            json={
                "tool_id": "uppercase",
                "tool_type": "local",
                "principal_type": "user",
                "user_id": str(keycloak_id),
                "email": "db@test.com",
                "email_verified": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
