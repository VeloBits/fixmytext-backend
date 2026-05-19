"""Tests for /api/v1/subscription/* endpoints."""

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# ── GET /subscription/status ─────────────────────────────────────────────────


def test_subscription_status_success(client, mock_db, fake_user):
    """Authenticated user gets subscription status with usage info."""
    with (
        patch("app.api.v1.endpoints.subscription.resolve_user_region", AsyncMock()),
        patch(
            "app.api.v1.endpoints.subscription.get_all_tool_uses_today",
            AsyncMock(return_value={}),
        ),
        patch(
            "app.api.v1.endpoints.subscription.has_logged_in_today",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.api.v1.endpoints.subscription.record_daily_login",
            AsyncMock(),
        ),
        patch(
            "app.api.v1.endpoints.subscription.get_credit_balance",
            AsyncMock(return_value=0),
        ),
        patch(
            "app.api.v1.endpoints.subscription.get_active_passes",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.api.v1.endpoints.subscription.get_subscription_tier",
            AsyncMock(return_value="free"),
        ),
    ):
        resp = client.get("/api/v1/subscription/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "tier" in data
    assert "tool_uses_today" in data
    assert data["tier"] == "free"


def test_subscription_status_requires_auth(unauth_client):
    """Unauthenticated subscription status returns 401."""
    resp = unauth_client.get("/api/v1/subscription/status")
    assert resp.status_code == 401


# ── POST /subscription/checkout ──────────────────────────────────────────────


def test_checkout_payments_not_configured(client, mock_db):
    """When RAZORPAY_KEY_ID is empty, checkout returns 503."""
    from app.core.config import settings

    original = settings.RAZORPAY_KEY_ID
    settings.RAZORPAY_KEY_ID = ""

    # subscription tier check
    result = MagicMock()
    result.scalar.return_value = None
    mock_db.execute.return_value = result

    resp = client.post("/api/v1/subscription/checkout")
    settings.RAZORPAY_KEY_ID = original
    assert resp.status_code == 503


def test_checkout_already_pro(client, mock_db):
    """User already subscribed to Pro gets 400."""
    from app.core.config import settings

    original = settings.RAZORPAY_KEY_ID
    settings.RAZORPAY_KEY_ID = "rzp_test_xxx"

    result = MagicMock()
    result.scalar.return_value = "pro"  # already pro
    mock_db.execute.return_value = result

    resp = client.post("/api/v1/subscription/checkout")
    settings.RAZORPAY_KEY_ID = original
    assert resp.status_code == 400


def test_checkout_requires_auth(unauth_client):
    """Checkout requires authentication."""
    resp = unauth_client.post("/api/v1/subscription/checkout")
    assert resp.status_code == 401


# ── POST /subscription/cancel ────────────────────────────────────────────────


def test_cancel_no_active_sub(client, mock_db):
    """Cancelling with no active Pro subscription returns 400."""
    result = MagicMock()
    result.scalar.return_value = None  # not pro
    mock_db.execute.return_value = result

    resp = client.post("/api/v1/subscription/cancel")
    assert resp.status_code == 400


def test_cancel_requires_auth(unauth_client):
    """Cancel requires authentication."""
    resp = unauth_client.post("/api/v1/subscription/cancel")
    assert resp.status_code == 401


# ── POST /subscription/verify ────────────────────────────────────────────────


def test_verify_requires_auth(unauth_client):
    """Verify requires authentication."""
    resp = unauth_client.post(
        "/api/v1/subscription/verify",
        json={
            "razorpay_order_id": "order_xxx",
            "razorpay_payment_id": "pay_xxx",
            "razorpay_signature": "sig_xxx",
        },
    )
    assert resp.status_code == 401


# ── POST /subscription/webhook ───────────────────────────────────────────────


def test_webhook_no_secret_configured(anon_client, mock_db):
    """When webhook secret is not configured, returns 503."""
    from app.core.config import settings

    original = settings.RAZORPAY_WEBHOOK_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = ""

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        data=b'{"event":"test"}',
        headers={"x-razorpay-signature": "sig", "content-type": "application/json"},
    )
    settings.RAZORPAY_WEBHOOK_SECRET = original
    assert resp.status_code == 503


def test_webhook_invalid_signature(anon_client, mock_db):
    """Invalid webhook signature returns 400."""
    from app.core.config import settings

    original = settings.RAZORPAY_WEBHOOK_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = "test-secret"  # noqa: S105

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        data=b'{"event":"test"}',
        headers={
            "x-razorpay-signature": "bad-signature",
            "content-type": "application/json",
        },
    )
    settings.RAZORPAY_WEBHOOK_SECRET = original
    assert resp.status_code == 400


# ── Webhook happy-path tests ────────────────────────────────────────────────

WEBHOOK_SECRET = "test-webhook-secret"  # noqa: S105


def _sign_webhook(body: bytes) -> str:
    """Compute a valid HMAC-SHA256 signature for the given body."""
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _webhook_payload(
    event_type: str = "payment.captured",
    user_id: str | None = None,
    payment_id: str = "pay_test123",
    order_id: str = "order_test456",
    amount: int = 500,
    currency: str = "USD",
    item_type: str = "pro_subscription",
    item_id: str | None = None,
) -> bytes:
    """Build a Razorpay-style webhook JSON body."""
    uid = user_id or str(uuid.uuid4())
    payload = {
        "event": event_type,
        "account_id": "acc_test",
        "created_at": 1700000000,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount,
                    "currency": currency,
                    "error_description": "payment declined",
                    "notes": {
                        "user_id": uid,
                        "item_type": item_type,
                        "item_id": item_id,
                    },
                }
            }
        },
    }
    return json.dumps(payload).encode()


def _setup_webhook_secret():
    """Set the webhook secret; returns a restore function."""
    from app.core.config import settings

    original = settings.RAZORPAY_WEBHOOK_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = WEBHOOK_SECRET
    return lambda: setattr(settings, "RAZORPAY_WEBHOOK_SECRET", original)


def test_webhook_payment_authorized(anon_client, mock_db, fake_user):
    """payment.authorized event is acknowledged."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(event_type="payment.authorized", user_id=str(fake_user.id))
    sig = _sign_webhook(body)

    # mock: no duplicate event, flush succeeds
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = result

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_webhook_payment_failed(anon_client, mock_db, fake_user):
    """payment.failed event is acknowledged."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(event_type="payment.failed", user_id=str(fake_user.id))
    sig = _sign_webhook(body)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = result

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_webhook_duplicate_event_ignored(anon_client, mock_db, fake_user):
    """Duplicate events (already processed) are acknowledged but not reprocessed."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(user_id=str(fake_user.id))
    sig = _sign_webhook(body)

    # Simulate an already-processed event
    existing_event = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = existing_event
    mock_db.execute.return_value = result

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200
    assert resp.json()["detail"] == "duplicate"


def test_webhook_payment_captured_pro(anon_client, mock_db, fake_user):
    """payment.captured for pro_subscription creates a Subscription."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(
        event_type="payment.captured",
        user_id=str(fake_user.id),
        item_type="pro_subscription",
        amount=500,
        currency="USD",
    )
    sig = _sign_webhook(body)

    # First execute: idempotency check → no duplicate
    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    # Second execute: user lookup → returns user
    user_result = MagicMock()
    user_result.scalars.return_value.first.return_value = fake_user
    mock_db.execute.side_effect = [no_dup, user_result]

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    # Verify a Subscription was added
    mock_db.add.assert_called()


def test_webhook_payment_captured_missing_user_id(anon_client, mock_db):
    """payment.captured without user_id in notes returns 400."""
    restore = _setup_webhook_secret()
    payload = {
        "event": "payment.captured",
        "account_id": "acc_test",
        "created_at": 1700000000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_x",
                    "order_id": "order_x",
                    "amount": 500,
                    "currency": "USD",
                    "notes": {"item_type": "pro_subscription"},
                }
            }
        },
    }
    body = json.dumps(payload).encode()
    sig = _sign_webhook(body)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = result

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 400


def test_webhook_payment_captured_user_not_found(anon_client, mock_db):
    """payment.captured for a non-existent user returns 400."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(
        event_type="payment.captured",
        user_id=str(uuid.uuid4()),
        item_type="pro_subscription",
    )
    sig = _sign_webhook(body)

    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    no_user = MagicMock()
    no_user.scalars.return_value.first.return_value = None
    mock_db.execute.side_effect = [no_dup, no_user]

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 400


def test_webhook_payment_captured_unknown_pass(anon_client, mock_db, fake_user):
    """payment.captured for an unknown pass returns 400."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(
        event_type="payment.captured",
        user_id=str(fake_user.id),
        item_type="pass",
        item_id="nonexistent_pass",
    )
    sig = _sign_webhook(body)

    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    user_result = MagicMock()
    user_result.scalars.return_value.first.return_value = fake_user
    mock_db.execute.side_effect = [no_dup, user_result]

    with patch("app.api.v1.endpoints.subscription.get_pass", return_value=None):
        resp = anon_client.post(
            "/api/v1/subscription/webhook",
            content=body,
            headers={
                "x-razorpay-signature": sig,
                "content-type": "application/json",
            },
        )
    restore()
    assert resp.status_code == 400


def test_webhook_payment_captured_pass_granted(anon_client, mock_db, fake_user):
    """payment.captured for a valid pass grants it."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(
        event_type="payment.captured",
        user_id=str(fake_user.id),
        item_type="pass",
        item_id="day_pass",
    )
    sig = _sign_webhook(body)

    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    user_result = MagicMock()
    user_result.scalars.return_value.first.return_value = fake_user
    mock_db.execute.side_effect = [no_dup, user_result]

    with (
        patch(
            "app.api.v1.endpoints.subscription.get_pass",
            return_value={"id": "day_pass", "name": "Day Pass", "duration_hours": 24},
        ),
        patch(
            "app.api.v1.endpoints.subscription.grant_pass", AsyncMock()
        ) as mock_grant,
    ):
        resp = anon_client.post(
            "/api/v1/subscription/webhook",
            content=body,
            headers={
                "x-razorpay-signature": sig,
                "content-type": "application/json",
            },
        )
    restore()
    assert resp.status_code == 200
    mock_grant.assert_called_once()


def test_webhook_payment_captured_unknown_credit_pack(anon_client, mock_db, fake_user):
    """payment.captured for an unknown credit pack returns 400."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(
        event_type="payment.captured",
        user_id=str(fake_user.id),
        item_type="credit",
        item_id="nonexistent_pack",
    )
    sig = _sign_webhook(body)

    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    user_result = MagicMock()
    user_result.scalars.return_value.first.return_value = fake_user
    mock_db.execute.side_effect = [no_dup, user_result]

    with patch("app.api.v1.endpoints.subscription.get_credit_pack", return_value=None):
        resp = anon_client.post(
            "/api/v1/subscription/webhook",
            content=body,
            headers={
                "x-razorpay-signature": sig,
                "content-type": "application/json",
            },
        )
    restore()
    assert resp.status_code == 400


def test_webhook_payment_captured_credits_granted(anon_client, mock_db, fake_user):
    """payment.captured for a valid credit pack grants credits."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(
        event_type="payment.captured",
        user_id=str(fake_user.id),
        item_type="credit",
        item_id="credit_100",
    )
    sig = _sign_webhook(body)

    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    user_result = MagicMock()
    user_result.scalars.return_value.first.return_value = fake_user
    mock_db.execute.side_effect = [no_dup, user_result]

    with (
        patch(
            "app.api.v1.endpoints.subscription.get_credit_pack",
            return_value={"id": "credit_100", "credits": 100},
        ),
        patch(
            "app.api.v1.endpoints.subscription.grant_credits", AsyncMock()
        ) as mock_grant,
    ):
        resp = anon_client.post(
            "/api/v1/subscription/webhook",
            content=body,
            headers={
                "x-razorpay-signature": sig,
                "content-type": "application/json",
            },
        )
    restore()
    assert resp.status_code == 200
    mock_grant.assert_called_once()


def test_webhook_payment_captured_unknown_item_type(anon_client, mock_db, fake_user):
    """payment.captured with an unknown item_type still succeeds (logged as warning)."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(
        event_type="payment.captured",
        user_id=str(fake_user.id),
        item_type="unknown_thing",
    )
    sig = _sign_webhook(body)

    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    user_result = MagicMock()
    user_result.scalars.return_value.first.return_value = fake_user
    mock_db.execute.side_effect = [no_dup, user_result]

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200


def test_webhook_subscription_cancelled(anon_client, mock_db, fake_user):
    """subscription.cancelled downgrades an active subscription."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(
        event_type="subscription.cancelled", user_id=str(fake_user.id)
    )
    sig = _sign_webhook(body)

    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    active_sub = MagicMock()
    active_sub.status = "active"
    sub_result = MagicMock()
    sub_result.scalars.return_value.first.return_value = active_sub
    mock_db.execute.side_effect = [no_dup, sub_result]

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200
    assert active_sub.status == "cancelled"


def test_webhook_subscription_halted(anon_client, mock_db, fake_user):
    """subscription.halted pauses an active subscription."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(event_type="subscription.halted", user_id=str(fake_user.id))
    sig = _sign_webhook(body)

    no_dup = MagicMock()
    no_dup.scalars.return_value.first.return_value = None
    active_sub = MagicMock()
    active_sub.status = "active"
    sub_result = MagicMock()
    sub_result.scalars.return_value.first.return_value = active_sub
    mock_db.execute.side_effect = [no_dup, sub_result]

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200
    assert active_sub.status == "halted"


def test_webhook_unhandled_event(anon_client, mock_db, fake_user):
    """Unrecognised events are acknowledged but not processed."""
    restore = _setup_webhook_secret()
    body = _webhook_payload(event_type="some.future.event", user_id=str(fake_user.id))
    sig = _sign_webhook(body)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = result

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_webhook_invalid_json(anon_client, mock_db):
    """Malformed JSON body returns 400."""
    restore = _setup_webhook_secret()
    body = b"not valid json"
    sig = _sign_webhook(body)

    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 400


def test_webhook_log_injection_prevented(anon_client, mock_db, fake_user):
    """Newlines in webhook values are stripped from log output."""
    restore = _setup_webhook_secret()
    payload = {
        "event": "payment.authorized\nINFO [fake] forged entry",
        "account_id": "acc_evil\rline",
        "created_at": 1700000000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test\ninjection",
                    "order_id": "order_test",
                    "amount": 500,
                    "currency": "USD",
                    "notes": {
                        "user_id": str(fake_user.id),
                        "item_type": "pro_subscription",
                    },
                }
            }
        },
    }
    body = json.dumps(payload).encode()
    sig = _sign_webhook(body)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = result

    # Should not raise — newlines are handled gracefully
    resp = anon_client.post(
        "/api/v1/subscription/webhook",
        content=body,
        headers={"x-razorpay-signature": sig, "content-type": "application/json"},
    )
    restore()
    assert resp.status_code == 200


# ── Checkout success ────────────────────────────────────────────────────────


def test_checkout_success(client, mock_db, fake_user):
    """Successful checkout creates a Razorpay order."""
    from app.core.config import settings

    original_key = settings.RAZORPAY_KEY_ID
    settings.RAZORPAY_KEY_ID = "rzp_test_key"  # noqa: S105

    with (
        patch(
            "app.api.v1.endpoints.subscription.get_subscription_tier",
            AsyncMock(return_value="free"),
        ),
        patch(
            "app.api.v1.endpoints.subscription.create_order",
            return_value={
                "id": "order_test_123",
                "amount": 500,
                "currency": "USD",
            },
        ),
    ):
        resp = client.post("/api/v1/subscription/checkout")

    settings.RAZORPAY_KEY_ID = original_key
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_id"] == "order_test_123"
    assert data["amount"] == 500


def test_checkout_razorpay_failure(client, mock_db, fake_user):
    """Razorpay API failure returns 502."""
    from app.core.config import settings

    original_key = settings.RAZORPAY_KEY_ID
    settings.RAZORPAY_KEY_ID = "rzp_test_key"  # noqa: S105

    with (
        patch(
            "app.api.v1.endpoints.subscription.get_subscription_tier",
            AsyncMock(return_value="free"),
        ),
        patch(
            "app.api.v1.endpoints.subscription.create_order",
            side_effect=RuntimeError("API down"),
        ),
    ):
        resp = client.post("/api/v1/subscription/checkout")

    settings.RAZORPAY_KEY_ID = original_key
    assert resp.status_code == 502


# ── Verify payment ──────────────────────────────────────────────────────────


def test_verify_invalid_signature(client, mock_db, fake_user):
    """Invalid Razorpay signature returns 400."""
    with patch(
        "app.api.v1.endpoints.subscription.verify_payment_signature",
        return_value=False,
    ):
        resp = client.post(
            "/api/v1/subscription/verify",
            json={
                "razorpay_order_id": "order_xxx",
                "razorpay_payment_id": "pay_xxx",
                "razorpay_signature": "sig_xxx",
            },
        )
    assert resp.status_code == 400


def test_verify_success(client, mock_db, fake_user):
    """Valid payment verification activates Pro."""
    with (
        patch(
            "app.api.v1.endpoints.subscription.verify_payment_signature",
            return_value=True,
        ),
        patch(
            "app.api.v1.endpoints.subscription.fetch_order",
            return_value={
                "notes": {
                    "user_id": str(fake_user.id),
                    "item_type": "pro_subscription",
                },
                "amount": 500,
                "currency": "USD",
            },
        ),
    ):
        resp = client.post(
            "/api/v1/subscription/verify",
            json={
                "razorpay_order_id": "order_xxx",
                "razorpay_payment_id": "pay_xxx",
                "razorpay_signature": "sig_xxx",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["tier"] == "pro"


def test_verify_order_user_mismatch(client, mock_db, fake_user):
    """Order belonging to a different user returns 400."""
    with (
        patch(
            "app.api.v1.endpoints.subscription.verify_payment_signature",
            return_value=True,
        ),
        patch(
            "app.api.v1.endpoints.subscription.fetch_order",
            return_value={
                "notes": {
                    "user_id": str(uuid.uuid4()),  # different user
                    "item_type": "pro_subscription",
                },
            },
        ),
    ):
        resp = client.post(
            "/api/v1/subscription/verify",
            json={
                "razorpay_order_id": "order_xxx",
                "razorpay_payment_id": "pay_xxx",
                "razorpay_signature": "sig_xxx",
            },
        )
    assert resp.status_code == 400


def test_verify_order_wrong_item_type(client, mock_db, fake_user):
    """Order with wrong item_type returns 400."""
    with (
        patch(
            "app.api.v1.endpoints.subscription.verify_payment_signature",
            return_value=True,
        ),
        patch(
            "app.api.v1.endpoints.subscription.fetch_order",
            return_value={
                "notes": {
                    "user_id": str(fake_user.id),
                    "item_type": "credit",
                },
            },
        ),
    ):
        resp = client.post(
            "/api/v1/subscription/verify",
            json={
                "razorpay_order_id": "order_xxx",
                "razorpay_payment_id": "pay_xxx",
                "razorpay_signature": "sig_xxx",
            },
        )
    assert resp.status_code == 400


def test_verify_fetch_order_failure(client, mock_db, fake_user):
    """Razorpay fetch_order failure returns 502."""
    with (
        patch(
            "app.api.v1.endpoints.subscription.verify_payment_signature",
            return_value=True,
        ),
        patch(
            "app.api.v1.endpoints.subscription.fetch_order",
            side_effect=RuntimeError("API error"),
        ),
    ):
        resp = client.post(
            "/api/v1/subscription/verify",
            json={
                "razorpay_order_id": "order_xxx",
                "razorpay_payment_id": "pay_xxx",
                "razorpay_signature": "sig_xxx",
            },
        )
    assert resp.status_code == 502


# ── Cancel subscription ────────────────────────────────────────────────────


def test_cancel_success(client, mock_db, fake_user):
    """Cancel an active Pro subscription."""
    active_sub = MagicMock()
    active_sub.status = "active"

    tier_result = MagicMock()
    tier_result.scalar.return_value = "pro"
    sub_result = MagicMock()
    sub_result.scalars.return_value.first.return_value = active_sub
    mock_db.execute.side_effect = [tier_result, sub_result]

    with patch(
        "app.api.v1.endpoints.subscription.get_subscription_tier",
        AsyncMock(return_value="pro"),
    ):
        resp = client.post("/api/v1/subscription/cancel")

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ── Status endpoint ──────────────────────────────────────────────────────


def test_subscription_status_no_region_resolves(client, mock_db, fake_user):
    """User without region triggers region resolution."""
    fake_user.region = None

    with (
        patch(
            "app.api.v1.endpoints.subscription.resolve_user_region",
            AsyncMock(),
        ) as mock_resolve,
        patch(
            "app.api.v1.endpoints.subscription.get_all_tool_uses_today",
            AsyncMock(return_value={}),
        ),
        patch(
            "app.api.v1.endpoints.subscription.has_logged_in_today",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.api.v1.endpoints.subscription.record_daily_login",
            AsyncMock(),
        ),
        patch(
            "app.api.v1.endpoints.subscription.get_credit_balance",
            AsyncMock(return_value=0),
        ),
        patch(
            "app.api.v1.endpoints.subscription.get_active_passes",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.api.v1.endpoints.subscription.get_subscription_tier",
            AsyncMock(return_value="free"),
        ),
    ):
        resp = client.get("/api/v1/subscription/status")

    fake_user.region = "US"  # restore
    assert resp.status_code == 200
    mock_resolve.assert_called_once()


# ── _validate_payment_amount ────────────────────────────────────────────────


def test_validate_payment_amount_mismatch_logs_warning():
    """Mismatched payment amount logs a warning."""
    import logging

    from app.api.v1.endpoints.subscription import _validate_payment_amount

    uid = uuid.uuid4()
    with patch.object(
        logging.getLogger("app.api.v1.endpoints.subscription"), "warning"
    ) as mock_warn:
        _validate_payment_amount("pro_subscription", None, 999, "USD", uid, "order_x")
    mock_warn.assert_called_once()


def test_validate_payment_amount_no_amount_returns_early():
    """No amount means nothing to validate."""
    from app.api.v1.endpoints.subscription import _validate_payment_amount

    # Should not raise
    _validate_payment_amount("pro_subscription", None, None, "USD", uuid.uuid4(), "o")


def test_validate_payment_amount_no_item_type_returns_early():
    """No item_type means nothing to validate."""
    from app.api.v1.endpoints.subscription import _validate_payment_amount

    _validate_payment_amount(None, None, 500, "USD", uuid.uuid4(), "o")


def test_validate_payment_amount_pass_match():
    """Matching pass price does not log a warning."""
    import logging

    from app.api.v1.endpoints.subscription import _validate_payment_amount

    with (
        patch("app.api.v1.endpoints.subscription.get_price", return_value=500),
        patch.object(
            logging.getLogger("app.api.v1.endpoints.subscription"), "warning"
        ) as mock_warn,
    ):
        _validate_payment_amount(
            "pass", "day_pass", 500, "INR", uuid.uuid4(), "order_x"
        )
    mock_warn.assert_not_called()
