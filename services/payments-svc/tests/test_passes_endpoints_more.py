"""Authenticated passes endpoint tests: /active, /order, /credit-order,
/verify, /spin, /referral-code, and /claim-referral.

Complements test_payments_endpoints.py (public catalog + auth guards).
No live DB or Razorpay required.
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.services.fulfillment_service import AlreadyFulfilled

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_user(region: str | None = "IN") -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.keycloak_id = uuid.uuid4()
    u.email = "passes@example.com"
    u.display_name = "Pass User"
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


# ── GET /passes/active ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_active_returns_passes_and_credits(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    active_pass = SimpleNamespace(
        id=uuid.uuid4(),
        pass_id="day_all",
        tools=[SimpleNamespace(tool_id="*")],
        tools_count=-1,
        uses_per_day=50,
        uses_today=2,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        source="razorpay",
    )
    active_credit = SimpleNamespace(
        id=uuid.uuid4(),
        credits_remaining=7,
        credits_total=15,
        source="purchase",
    )

    try:
        with (
            patch(
                "app.api.v1.endpoints.passes.get_active_passes",
                new_callable=AsyncMock,
                return_value=[active_pass],
            ),
            patch(
                "app.api.v1.endpoints.passes.get_active_credits",
                new_callable=AsyncMock,
                return_value=[active_credit],
            ),
            patch(
                "app.api.v1.endpoints.passes.get_credit_balance",
                new_callable=AsyncMock,
                return_value=7,
            ),
        ):
            response = await async_client.get("/api/v1/passes/active", headers=_AUTH)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["total_credits"] == 7
    assert len(data["passes"]) == 1
    assert data["passes"][0]["pass_id"] == "day_all"
    assert data["passes"][0]["name"] == "Day All"
    assert data["passes"][0]["tool_ids"] == ["*"]
    assert len(data["credits"]) == 1
    assert data["credits"][0]["credits_remaining"] == 7


# ── POST /passes/order ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pass_order_payments_not_configured_returns_503(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with patch(
            "app.api.v1.endpoints.passes.payments_configured", return_value=False
        ):
            response = await async_client.post(
                "/api/v1/passes/order",
                json={"pass_id": "quick_fix", "tool_ids": ["uppercase"]},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_pass_order_unknown_pass_returns_400(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with (
            patch("app.api.v1.endpoints.passes.payments_configured", return_value=True),
            patch(
                "app.api.v1.endpoints.passes.check_rate_limit",
                new_callable=AsyncMock,
            ),
        ):
            response = await async_client.post(
                "/api/v1/passes/order",
                json={"pass_id": "nonexistent_pass", "tool_ids": []},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "unknown pass" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pass_order_happy_path_creates_razorpay_order(async_client, app):
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

    try:
        with (
            patch("app.api.v1.endpoints.passes.payments_configured", return_value=True),
            patch(
                "app.api.v1.endpoints.passes.check_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.region_service.resolve_user_region",
                new_callable=AsyncMock,
                return_value="IN",
            ),
            patch(
                "app.api.v1.endpoints.passes.create_order",
                return_value={"id": "order_pass_1", "amount": 200, "currency": "INR"},
            ) as mock_create,
        ):
            response = await async_client.post(
                "/api/v1/passes/order",
                json={"pass_id": "quick_fix", "tool_ids": ["uppercase"]},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == "order_pass_1"
    assert data["amount"] == 200
    notes = mock_create.call_args.kwargs["notes"]
    assert notes["item_id"] == "quick_fix"
    assert notes["item_type"] == "pass"
    assert notes["tool_ids"] == "uppercase"
    assert notes["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_pass_order_razorpay_failure_returns_502(async_client, app):
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

    try:
        with (
            patch("app.api.v1.endpoints.passes.payments_configured", return_value=True),
            patch(
                "app.api.v1.endpoints.passes.check_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.region_service.resolve_user_region",
                new_callable=AsyncMock,
                return_value="IN",
            ),
            patch(
                "app.api.v1.endpoints.passes.create_order",
                side_effect=RuntimeError("razorpay down"),
            ),
        ):
            response = await async_client.post(
                "/api/v1/passes/order",
                json={"pass_id": "quick_fix", "tool_ids": ["uppercase"]},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502


# ── POST /passes/credit-order ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_credit_order_unknown_pack_returns_400(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with (
            patch("app.api.v1.endpoints.passes.payments_configured", return_value=True),
            patch(
                "app.api.v1.endpoints.passes.check_rate_limit",
                new_callable=AsyncMock,
            ),
        ):
            response = await async_client.post(
                "/api/v1/passes/credit-order",
                json={"pack_id": "credits_9999"},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "unknown credit pack" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_credit_order_happy_path_creates_razorpay_order(async_client, app):
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

    try:
        with (
            patch("app.api.v1.endpoints.passes.payments_configured", return_value=True),
            patch(
                "app.api.v1.endpoints.passes.check_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.region_service.resolve_user_region",
                new_callable=AsyncMock,
                return_value="IN",
            ),
            patch(
                "app.api.v1.endpoints.passes.create_order",
                return_value={"id": "order_cr_1", "amount": 500, "currency": "INR"},
            ) as mock_create,
        ):
            response = await async_client.post(
                "/api/v1/passes/credit-order",
                json={"pack_id": "credits_5"},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["order_id"] == "order_cr_1"
    notes = mock_create.call_args.kwargs["notes"]
    assert notes["item_id"] == "credits_5"
    assert notes["item_type"] == "credit"


@pytest.mark.asyncio
async def test_credit_order_razorpay_failure_returns_502(async_client, app):
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

    try:
        with (
            patch("app.api.v1.endpoints.passes.payments_configured", return_value=True),
            patch(
                "app.api.v1.endpoints.passes.check_rate_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.region_service.resolve_user_region",
                new_callable=AsyncMock,
                return_value="IN",
            ),
            patch(
                "app.api.v1.endpoints.passes.create_order",
                side_effect=RuntimeError("razorpay down"),
            ),
        ):
            response = await async_client.post(
                "/api/v1/passes/credit-order",
                json={"pack_id": "credits_5"},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502


# ── POST /passes/verify ──────────────────────────────────────────────────────


def _verify_body(item_id: str = "credits_5", item_type: str = "credit") -> dict:
    return {
        "razorpay_order_id": "order_v_1",
        "razorpay_payment_id": "pay_v_1",
        "razorpay_signature": "sig",
        "item_id": item_id,
        "item_type": item_type,
    }


@pytest.mark.asyncio
async def test_verify_pass_payment_credit_happy_path(async_client, app):
    """Valid credit order → fulfilled once + welcome gift check performed."""
    user = _make_user()
    db = _mock_db()
    _override(app, user, db)

    order = {
        "amount": 500,
        "currency": "inr",
        "notes": {
            "user_id": str(user.id),
            "item_id": "credits_5",
            "item_type": "credit",
        },
    }
    try:
        with (
            patch(
                "app.api.v1.endpoints.passes.verify_razorpay_payment",
                new_callable=AsyncMock,
                return_value=order,
            ),
            patch(
                "app.api.v1.endpoints.passes.fulfill_payment",
                new_callable=AsyncMock,
            ) as mock_fulfill,
            patch(
                "app.api.v1.endpoints.passes.maybe_grant_welcome_gift",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_gift,
        ):
            response = await async_client.post(
                "/api/v1/passes/verify", json=_verify_body(), headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "welcome_gift": True,
        "welcome_credits": 10,
    }
    mock_fulfill.assert_awaited_once()
    assert mock_fulfill.await_args.kwargs["item_type"] == "credit"
    assert mock_fulfill.await_args.kwargs["amount_subunits"] == 500
    mock_gift.assert_awaited_once()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_verify_pass_payment_item_mismatch_refunds(async_client, app):
    """Order notes disagreeing with the claimed item → captured money is
    auto-refunded exactly once (signature was valid, so this is a real
    payment we cannot fulfil) and the client learns via status=refunded."""
    user = _make_user()
    _override(app, user, _mock_db())

    order = {
        "amount": 1200,
        "currency": "inr",
        "notes": {
            "user_id": str(user.id),
            "item_id": "credits_15",  # client claims credits_5
            "item_type": "credit",
        },
    }
    try:
        with (
            patch(
                "app.api.v1.endpoints.passes.verify_razorpay_payment",
                new_callable=AsyncMock,
                return_value=order,
            ),
            patch(
                "app.api.v1.endpoints.passes.fulfill_payment",
                new_callable=AsyncMock,
            ) as mock_fulfill,
            patch(
                "app.api.v1.endpoints.passes.refund_unfulfillable_payment",
                new_callable=AsyncMock,
            ) as mock_refund,
        ):
            response = await async_client.post(
                "/api/v1/passes/verify", json=_verify_body(), headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "refunded"
    mock_fulfill.assert_not_awaited()
    mock_refund.assert_awaited_once()
    assert mock_refund.call_args.kwargs["via"] == "verify"


@pytest.mark.asyncio
async def test_verify_pass_payment_already_fulfilled_is_idempotent(async_client, app):
    user = _make_user()
    db = _mock_db()
    _override(app, user, db)

    order = {
        "amount": 500,
        "currency": "inr",
        "notes": {
            "user_id": str(user.id),
            "item_id": "credits_5",
            "item_type": "credit",
        },
    }
    try:
        with (
            patch(
                "app.api.v1.endpoints.passes.verify_razorpay_payment",
                new_callable=AsyncMock,
                return_value=order,
            ),
            patch(
                "app.api.v1.endpoints.passes.fulfill_payment",
                new_callable=AsyncMock,
                side_effect=AlreadyFulfilled("pay_v_1"),
            ),
        ):
            response = await async_client.post(
                "/api/v1/passes/verify", json=_verify_body(), headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["detail"] == "already_fulfilled"
    db.rollback.assert_awaited()


# ── POST /passes/spin ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spin_already_spun_returns_400(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with patch(
            "app.api.v1.endpoints.passes.spin_wheel",
            new_callable=AsyncMock,
            return_value={"error": "Already spun this week. Come back next week!"},
        ):
            response = await async_client.post("/api/v1/passes/spin", headers=_AUTH)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "already spun" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_spin_returns_credit_reward(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with patch(
            "app.api.v1.endpoints.passes.spin_wheel",
            new_callable=AsyncMock,
            return_value={
                "reward_type": "credits",
                "amount": 3,
                "message": "You won 3 credits!",
            },
        ):
            response = await async_client.post("/api/v1/passes/spin", headers=_AUTH)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["reward_type"] == "credits"
    assert data["amount"] == 3


# ── Referral endpoints ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_referral_code_returned_with_signup_url(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with patch(
            "app.api.v1.endpoints.passes.ensure_referral_code",
            new_callable=AsyncMock,
            return_value="ABCD123456",
        ):
            response = await async_client.get(
                "/api/v1/passes/referral-code", headers=_AUTH
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["referral_code"] == "ABCD123456"
    assert data["referral_url"].endswith("/signup?ref=ABCD123456")


@pytest.mark.asyncio
async def test_claim_referral_error_returns_400(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with patch(
            "app.api.v1.endpoints.passes.claim_referral",
            new_callable=AsyncMock,
            return_value={"error": "Invalid referral code."},
        ):
            response = await async_client.post(
                "/api/v1/passes/claim-referral",
                json={"code": "BADCODE"},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "invalid referral code" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_claim_referral_success_returns_result(async_client, app):
    user = _make_user()
    _override(app, user, _mock_db())

    try:
        with patch(
            "app.api.v1.endpoints.passes.claim_referral",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "message": "Referral claimed! You got 10 credits.",
            },
        ):
            response = await async_client.post(
                "/api/v1/passes/claim-referral",
                json={"code": "GOODCODE"},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["success"] is True


# ── POST /passes/order - order-time tool-scope validation (strict flag) ──────


def _order_patches(stack):
    """Enter the common /passes/order patches on an ExitStack."""
    stack.enter_context(
        patch("app.api.v1.endpoints.passes.payments_configured", return_value=True)
    )
    stack.enter_context(
        patch("app.api.v1.endpoints.passes.check_rate_limit", new_callable=AsyncMock)
    )
    stack.enter_context(
        patch(
            "app.services.region_service.resolve_user_region",
            new_callable=AsyncMock,
            return_value="IN",
        )
    )


@pytest.mark.asyncio
async def test_pass_order_strict_rejects_wrong_tool_count(async_client, app):
    """Strict mode: a scoped pass ordered with the wrong tool count fails at
    ORDER time - before any money can move (the Critical paid-but-nothing
    bug)."""
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

    try:
        with ExitStack() as stack:
            _order_patches(stack)
            stack.enter_context(
                patch.object(settings, "PASS_ORDER_STRICT_TOOL_SCOPE", True)
            )
            mock_create = stack.enter_context(
                patch("app.api.v1.endpoints.passes.create_order")
            )
            response = await async_client.post(
                "/api/v1/passes/order",
                json={"pass_id": "day_triple", "tool_ids": []},  # needs exactly 3
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "exactly 3 tools" in response.json()["detail"].lower()
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_pass_order_strict_accepts_exact_tool_count(async_client, app):
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

    try:
        with ExitStack() as stack:
            _order_patches(stack)
            stack.enter_context(
                patch.object(settings, "PASS_ORDER_STRICT_TOOL_SCOPE", True)
            )
            mock_create = stack.enter_context(
                patch(
                    "app.api.v1.endpoints.passes.create_order",
                    return_value={"id": "order_x", "amount": 2500, "currency": "INR"},
                )
            )
            response = await async_client.post(
                "/api/v1/passes/order",
                json={
                    "pass_id": "day_triple",
                    "tool_ids": ["uppercase", "translate", "grammar_fix"],
                },
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    notes = mock_create.call_args.kwargs["notes"]
    assert notes["tool_ids"] == "uppercase,translate,grammar_fix"


@pytest.mark.asyncio
async def test_pass_order_lenient_mode_still_accepts_empty_scope(async_client, app):
    """Rollout flag OFF: legacy clients sending [] still get an order (their
    captured payments are auto-refunded at fulfillment instead)."""
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

    try:
        with ExitStack() as stack:
            _order_patches(stack)
            stack.enter_context(
                patch.object(settings, "PASS_ORDER_STRICT_TOOL_SCOPE", False)
            )
            stack.enter_context(
                patch(
                    "app.api.v1.endpoints.passes.create_order",
                    return_value={"id": "order_y", "amount": 2500, "currency": "INR"},
                )
            )
            response = await async_client.post(
                "/api/v1/passes/order",
                json={"pass_id": "day_triple", "tool_ids": []},
                headers=_AUTH,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_pass_order_idempotency_key_varies_with_tool_scope(async_client, app):
    """Two orders for the SAME pass with DIFFERENT tools must use different
    idempotency keys - otherwise Razorpay's unpaid-order reuse would silently
    grant the first selection. Same tools → same key. Keys fit the 40-char
    receipt cap untruncated."""
    user = _make_user(region="IN")
    _override(app, user, _mock_db())

    async def _order(tool_ids):
        with ExitStack() as stack:
            _order_patches(stack)
            stack.enter_context(
                patch.object(settings, "PASS_ORDER_STRICT_TOOL_SCOPE", True)
            )
            mock_create = stack.enter_context(
                patch(
                    "app.api.v1.endpoints.passes.create_order",
                    return_value={"id": "order_z", "amount": 200, "currency": "INR"},
                )
            )
            response = await async_client.post(
                "/api/v1/passes/order",
                json={"pass_id": "quick_fix", "tool_ids": tool_ids},
                headers=_AUTH,
            )
        assert response.status_code == 200
        return mock_create.call_args.kwargs["idempotency_key"]

    try:
        key_a = await _order(["uppercase"])
        key_b = await _order(["translate"])
        key_a2 = await _order(["uppercase"])
    finally:
        app.dependency_overrides.clear()

    assert key_a != key_b
    assert key_a == key_a2
    assert len(key_a) <= 40
