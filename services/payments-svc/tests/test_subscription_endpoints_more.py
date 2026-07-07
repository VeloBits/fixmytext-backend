"""Additional subscription endpoint tests: checkout happy/error paths,
Pro payment verification, cancellation, and region resolution on /status.

Complements test_payments_auth.py (status shape, daily bonus, already-Pro
and not-configured checkout guards). No live DB or Razorpay required.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.deps import get_current_user
from app.db.session import get_db
from app.services.fulfillment_service import AlreadyFulfilled

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_user(region: str | None = "IN") -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.keycloak_id = uuid.uuid4()
    u.email = "pro@example.com"
    u.display_name = "Pro User"
    u.is_active = True
    u.is_email_verified = True
    u.region = region
    return u


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[]),
                    first=MagicMock(return_value=None),
                )
            )
        )
    )
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _override(app, user, db):
    async def _override_db():
        yield db

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _override_db


_AUTH = {"Authorization": "Bearer valid.token"}


# ── POST /subscription/checkout ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkout_happy_path_creates_order_with_regional_price(async_client, app):
    """Free-tier IN user → 200 with the Razorpay order and INR Pro pricing."""
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

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
                "app.api.v1.endpoints.subscription.get_subscription_tier",
                new_callable=AsyncMock,
                return_value="free",
            ),
            patch(
                "app.api.v1.endpoints.subscription.create_order",
                return_value={"id": "order_pro_1", "amount": 39900, "currency": "INR"},
            ) as mock_create,
        ):
            response = await async_client.post(
                "/api/v1/subscription/checkout", headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == "order_pro_1"
    assert data["amount"] == 39900
    assert data["currency"] == "INR"
    assert data["user_email"] == "pro@example.com"
    assert mock_create.call_args.kwargs["amount"] == 39900
    assert mock_create.call_args.kwargs["currency"] == "INR"
    notes = mock_create.call_args.kwargs["notes"]
    assert notes == {"user_id": str(user.id), "item_type": "pro_subscription"}


@pytest.mark.asyncio
async def test_checkout_razorpay_failure_returns_502(async_client, app):
    """A Razorpay outage during order creation surfaces as 502, not 500."""
    user = _make_user()
    _override(app, user, _mock_db())

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
                "app.api.v1.endpoints.subscription.get_subscription_tier",
                new_callable=AsyncMock,
                return_value="free",
            ),
            patch(
                "app.api.v1.endpoints.subscription.create_order",
                side_effect=RuntimeError("razorpay down"),
            ),
        ):
            response = await async_client.post(
                "/api/v1/subscription/checkout", headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502


# ── POST /subscription/verify ────────────────────────────────────────────────

_VERIFY_BODY = {
    "razorpay_order_id": "order_pro_1",
    "razorpay_payment_id": "pay_pro_1",
    "razorpay_signature": "sig",
}


@pytest.mark.asyncio
async def test_verify_invalid_signature_returns_400(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with patch(
            "app.api.v1.endpoints.subscription.verify_payment_signature",
            return_value=False,
        ):
            response = await async_client.post(
                "/api/v1/subscription/verify", json=_VERIFY_BODY, headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "invalid signature" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_verify_order_fetch_failure_returns_502(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.verify_payment_signature",
                return_value=True,
            ),
            patch(
                "app.api.v1.endpoints.subscription.fetch_order",
                side_effect=RuntimeError("api down"),
            ),
        ):
            response = await async_client.post(
                "/api/v1/subscription/verify", json=_VERIFY_BODY, headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_verify_order_owned_by_other_user_returns_400(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    order = {
        "amount": 39900,
        "currency": "INR",
        "notes": {"user_id": str(uuid.uuid4()), "item_type": "pro_subscription"},
    }
    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.verify_payment_signature",
                return_value=True,
            ),
            patch(
                "app.api.v1.endpoints.subscription.fetch_order",
                return_value=order,
            ),
        ):
            response = await async_client.post(
                "/api/v1/subscription/verify", json=_VERIFY_BODY, headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"]


@pytest.mark.asyncio
async def test_verify_order_not_for_pro_returns_400(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    order = {
        "amount": 500,
        "currency": "inr",
        "notes": {"user_id": str(user.id), "item_type": "credit"},
    }
    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.verify_payment_signature",
                return_value=True,
            ),
            patch(
                "app.api.v1.endpoints.subscription.fetch_order",
                return_value=order,
            ),
        ):
            response = await async_client.post(
                "/api/v1/subscription/verify", json=_VERIFY_BODY, headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "not for pro" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_verify_happy_path_activates_pro(async_client, app):
    user = _make_user()
    db = _mock_db()
    _override(app, user, db)

    order = {
        "amount": 39900,
        "currency": "INR",
        "notes": {"user_id": str(user.id), "item_type": "pro_subscription"},
    }
    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.verify_payment_signature",
                return_value=True,
            ),
            patch(
                "app.api.v1.endpoints.subscription.fetch_order",
                return_value=order,
            ),
            patch(
                "app.api.v1.endpoints.subscription.fulfill_payment",
                new_callable=AsyncMock,
            ) as mock_fulfill,
        ):
            response = await async_client.post(
                "/api/v1/subscription/verify", json=_VERIFY_BODY, headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "success", "tier": "pro"}
    mock_fulfill.assert_awaited_once()
    assert mock_fulfill.await_args.kwargs["fulfilled_via"] == "verify"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_verify_already_fulfilled_is_idempotent_success(async_client, app):
    user = _make_user()
    db = _mock_db()
    _override(app, user, db)

    order = {
        "amount": 39900,
        "currency": "INR",
        "notes": {"user_id": str(user.id), "item_type": "pro_subscription"},
    }
    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.verify_payment_signature",
                return_value=True,
            ),
            patch(
                "app.api.v1.endpoints.subscription.fetch_order",
                return_value=order,
            ),
            patch(
                "app.api.v1.endpoints.subscription.fulfill_payment",
                new_callable=AsyncMock,
                side_effect=AlreadyFulfilled("pay_pro_1"),
            ),
        ):
            response = await async_client.post(
                "/api/v1/subscription/verify", json=_VERIFY_BODY, headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["detail"] == "already_fulfilled"
    db.rollback.assert_awaited()


# ── POST /subscription/cancel ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_without_active_pro_returns_400(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with patch(
            "app.api.v1.endpoints.subscription.get_subscription_tier",
            new_callable=AsyncMock,
            return_value="free",
        ):
            response = await async_client.post(
                "/api/v1/subscription/cancel", headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "no active pro" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cancel_active_pro_marks_subscription_cancelled(async_client, app):
    user = _make_user()
    active_sub = SimpleNamespace(status="active", cancelled_at=None)
    db = _mock_db()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=active_sub))
            )
        )
    )
    _override(app, user, db)

    try:
        with patch(
            "app.api.v1.endpoints.subscription.get_subscription_tier",
            new_callable=AsyncMock,
            return_value="pro",
        ):
            response = await async_client.post(
                "/api/v1/subscription/cancel", headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "cancelled"}
    assert active_sub.status == "cancelled"
    assert active_sub.cancelled_at is not None
    db.commit.assert_awaited()


# ── GET /subscription/status — region resolution ─────────────────────────────


@pytest.mark.asyncio
async def test_status_resolves_region_when_missing(async_client, app):
    """A user without a stored region triggers resolve_user_region + commit."""
    user = _make_user(region=None)
    db = _mock_db()
    _override(app, user, db)

    try:
        with (
            patch(
                "app.api.v1.endpoints.subscription.resolve_user_region",
                new_callable=AsyncMock,
                return_value="US",
            ) as mock_resolve,
            patch(
                "app.api.v1.endpoints.subscription.get_all_tool_uses_today",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.api.v1.endpoints.subscription.has_logged_in_today",
                new_callable=AsyncMock,
                return_value=True,
            ),
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
            patch(
                "app.api.v1.endpoints.subscription.get_subscription_tier",
                new_callable=AsyncMock,
                return_value="free",
            ),
        ):
            response = await async_client.get(
                "/api/v1/subscription/status", headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    mock_resolve.assert_awaited_once()
    db.commit.assert_awaited()
