"""Auth-gated endpoint tests for payments-svc.

Covers gaps not in test_payments_endpoints.py:
- GET /subscription/status with valid auth → 200 with correct response shape
- GET /subscription/status first call of day → daily_login_bonus=True
- POST /subscription/checkout when already Pro → 400
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_user(region: str | None = "IN") -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.keycloak_id = uuid.uuid4()
    u.email = "sub@example.com"
    u.display_name = "Sub User"
    u.is_active = True
    u.is_email_verified = True
    u.region = region
    return u


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


# ── GET /subscription/status ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscription_status_returns_200_with_correct_shape(async_client, app):
    """GET /subscription/status with valid auth → 200 with all expected fields."""
    from app.core.deps import get_current_user
    from app.db.session import get_db

    user = _make_user()
    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _override_db

    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.get_all_tool_uses_today",
                new_callable=AsyncMock,
                return_value={"uppercase": 1},
            ),
            patch(
                "app.api.v1.endpoints.subscription.has_logged_in_today",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.api.v1.endpoints.subscription.record_daily_login",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.v1.endpoints.subscription.get_credit_balance",
                new_callable=AsyncMock,
                return_value=5,
            ),
            patch(
                "app.api.v1.endpoints.subscription.get_active_passes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            response = await async_client.get(
                "/api/v1/subscription/status",
                headers={"Authorization": "Bearer valid.token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "tier" in data
    assert "tool_uses_today" in data
    assert "free_uses_per_tool" in data
    assert "daily_login_bonus" in data
    assert "credit_balance" in data
    assert "active_passes_count" in data


@pytest.mark.asyncio
async def test_subscription_status_first_call_grants_daily_bonus(async_client, app):
    """First GET /subscription/status of the day returns daily_login_bonus=True."""
    from app.core.deps import get_current_user
    from app.db.session import get_db

    user = _make_user()
    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _override_db

    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.get_all_tool_uses_today",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.api.v1.endpoints.subscription.has_logged_in_today",
                new_callable=AsyncMock,
                return_value=False,  # first call of day
            ),
            patch(
                "app.api.v1.endpoints.subscription.record_daily_login",
                new_callable=AsyncMock,
            ) as mock_record,
            patch(
                "app.api.v1.endpoints.subscription.get_credit_balance",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "app.api.v1.endpoints.subscription.get_active_passes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            response = await async_client.get(
                "/api/v1/subscription/status",
                headers={"Authorization": "Bearer valid.token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["daily_login_bonus"] is True
    mock_record.assert_awaited_once()


# ── POST /subscription/checkout ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkout_already_pro_returns_400(async_client, app):
    """POST /subscription/checkout when user is already Pro → 400."""
    from app.core.deps import get_current_user
    from app.db.session import get_db

    user = _make_user()
    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _override_db

    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.payments_configured",
                return_value=True,
            ),
            patch(
                "app.api.v1.endpoints.subscription.check_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.v1.endpoints.subscription.get_pro_subscription",
                new_callable=AsyncMock,
                # Active sub with ~20 days left — outside the renewal window.
                return_value=SimpleNamespace(
                    status="active",
                    expires_at=datetime.now(UTC) + timedelta(days=20),
                ),
            ),
        ):
            response = await async_client.post(
                "/api/v1/subscription/checkout",
                headers={"Authorization": "Bearer valid.token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "subscribed until" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_checkout_payments_not_configured_returns_503(async_client, app):
    """POST /subscription/checkout when Razorpay is not configured → 503."""
    from app.core.deps import get_current_user
    from app.db.session import get_db

    user = _make_user()
    mock_db = _mock_db()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _override_db

    try:
        with patch(
            "app.api.v1.endpoints.subscription.payments_configured",
            return_value=False,
        ):
            response = await async_client.post(
                "/api/v1/subscription/checkout",
                headers={"Authorization": "Bearer valid.token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
