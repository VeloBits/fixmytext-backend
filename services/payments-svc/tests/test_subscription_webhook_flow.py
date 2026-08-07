"""Webhook flow tests for POST /api/v1/subscription/webhook.

Exercises every event branch of ``razorpay_webhook`` against a mocked DB
session with real HMAC signatures: idempotency (duplicate event id and the
concurrent-insert IntegrityError), payment.authorized / payment.failed
acknowledgements, payment.captured fulfillment (pro, credit, pass guards,
AlreadyFulfilled, unexpected errors), subscription.cancelled / halted, and
the unhandled-event acknowledgement.

No live DB or Razorpay connection required.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.session import get_db
from app.services.fulfillment_service import AlreadyFulfilled

_SECRET = "test-webhook-secret"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _result(*, first=None, scalar=None):
    res = MagicMock()
    res.scalars.return_value.first.return_value = first
    res.scalar.return_value = scalar
    return res


def _mock_db(execute_results=None):
    db = AsyncMock()
    db.add = MagicMock()
    if execute_results is None:
        db.execute = AsyncMock(return_value=_result())
    else:
        db.execute = AsyncMock(side_effect=list(execute_results))
    db.scalar = AsyncMock(return_value=None)
    return db


def _event(
    event_type: str,
    *,
    event_id: str = "evt_test_1",
    notes: dict | None = None,
    amount: int = 39900,
    currency: str = "INR",
    payment_id: str = "pay_test_1",
    order_id: str = "order_test_1",
) -> dict:
    return {
        "event": event_type,
        "id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount,
                    "currency": currency,
                    "notes": notes or {},
                    "error_description": "card declined",
                }
            }
        },
    }


async def _post_webhook(async_client, app, db, event=None, *, body: bytes = None):
    payload = body if body is not None else json.dumps(event).encode()

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        with patch.object(settings, "RAZORPAY_WEBHOOK_SECRET", _SECRET):
            return await async_client.post(
                "/api/v1/subscription/webhook",
                content=payload,
                headers={"x-razorpay-signature": _sign(payload)},
            )
    finally:
        app.dependency_overrides.clear()


def _added_payment_events(db):
    return [c.args[0] for c in db.add.call_args_list]


# ── Guards ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_secret_not_configured_returns_503(async_client, app):
    """No RAZORPAY_WEBHOOK_SECRET configured → 503, nothing processed."""
    db = _mock_db()

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        with patch.object(settings, "RAZORPAY_WEBHOOK_SECRET", ""):
            response = await async_client.post(
                "/api/v1/subscription/webhook",
                content=b"{}",
                headers={"x-razorpay-signature": "whatever"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_webhook_oversized_payload_returns_413(async_client, app):
    """Payload larger than WEBHOOK_MAX_BODY_BYTES → 413 before any processing."""
    db = _mock_db()

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        with (
            patch.object(settings, "RAZORPAY_WEBHOOK_SECRET", _SECRET),
            patch.object(settings, "WEBHOOK_MAX_BODY_BYTES", 10),
        ):
            body = b"x" * 100
            response = await async_client.post(
                "/api/v1/subscription/webhook",
                content=body,
                headers={"x-razorpay-signature": _sign(body)},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_invalid_json_returns_400(async_client, app):
    """A correctly signed but non-JSON body → 400 Invalid payload."""
    db = _mock_db()
    response = await _post_webhook(async_client, app, db, body=b"not-json{{")
    assert response.status_code == 400
    assert "invalid payload" in response.json()["detail"].lower()


# ── Idempotency ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_duplicate_event_id_acknowledged_not_reprocessed(
    async_client, app
):
    """An already-processed razorpay_event_id is acked with detail=duplicate."""
    existing = SimpleNamespace(id=uuid.uuid4(), status="processed")
    db = _mock_db([_result(first=existing)])

    event = _event("payment.captured", notes={"user_id": str(uuid.uuid4())})
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "duplicate"}
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_concurrent_insert_race_treated_as_duplicate(async_client, app):
    """IntegrityError on the PaymentEvent flush (concurrent delivery) → duplicate."""
    db = _mock_db([_result(first=None)])
    db.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))

    event = _event("payment.authorized", notes={"user_id": str(uuid.uuid4())})
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "duplicate"}
    db.rollback.assert_awaited()


# ── Malformed notes ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_malformed_user_id_returns_400_and_records_failed_event(
    async_client, app
):
    """A non-UUID user_id in notes → 400 with a status='failed' audit row."""
    db = _mock_db([_result(first=None)])

    event = _event("payment.captured", notes={"user_id": "not-a-uuid"})
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 400
    assert "invalid user_id" in response.json()["detail"].lower()
    events = _added_payment_events(db)
    assert len(events) == 1
    assert events[0].status == "failed"
    assert events[0].user_id is None


# ── Informational events ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_payment_authorized_marks_processed(async_client, app):
    db = _mock_db([_result(first=None)])

    event = _event("payment.authorized", notes={"user_id": str(uuid.uuid4())})
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"
    assert pe.processed_at is not None


@pytest.mark.asyncio
async def test_webhook_payment_failed_marks_processed(async_client, app):
    db = _mock_db([_result(first=None)])

    event = _event("payment.failed", notes={"user_id": str(uuid.uuid4())})
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"


# ── payment.captured ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_captured_missing_user_id_returns_400(async_client, app):
    db = _mock_db([_result(first=None)])

    event = _event("payment.captured", notes={"item_type": "pro_subscription"})
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 400
    assert "missing user_id" in response.json()["detail"].lower()
    pe = _added_payment_events(db)[0]
    assert pe.status == "failed"


@pytest.mark.asyncio
async def test_webhook_captured_pro_subscription_fulfills(async_client, app):
    """payment.captured for pro_subscription with a catalog-correct amount →
    fulfilled via the shared authority and the event marked processed."""
    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id=uuid.uuid4(), region="IN")
    db = _mock_db([_result(first=None), _result(first=user)])
    db.scalar = AsyncMock(return_value=user.keycloak_id)

    event = _event(
        "payment.captured",
        notes={"user_id": str(user.id), "item_type": "pro_subscription"},
        amount=39900,
        currency="INR",
    )
    with (
        patch(
            "app.api.v1.endpoints.subscription.fulfill_payment",
            new_callable=AsyncMock,
        ) as mock_fulfill,
        patch(
            "app.api.v1.endpoints.subscription.maybe_grant_welcome_gift",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_gift,
    ):
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_fulfill.assert_awaited_once()
    assert mock_fulfill.await_args.kwargs["fulfilled_via"] == "webhook"
    assert mock_fulfill.await_args.kwargs["item_type"] == "pro_subscription"
    # A first-ever purchase that happens to be Pro also earns the welcome gift.
    mock_gift.assert_awaited_once()
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"
    assert pe.keycloak_sub == str(user.keycloak_id)


@pytest.mark.asyncio
async def test_webhook_captured_pro_amount_mismatch_blocks_fulfillment(
    async_client, app
):
    """A tampered amount for an UNKNOWN user (no keycloak_sub resolvable, so
    no refund ledger row is possible) → 400, event failed, no grant.
    Known-user validation failures take the auto-refund path instead - see
    test_webhook_captured_validation_failure_auto_refunds."""
    user_id = uuid.uuid4()
    db = _mock_db([_result(first=None)])

    event = _event(
        "payment.captured",
        notes={"user_id": str(user_id), "item_type": "pro_subscription"},
        amount=1,  # not a catalog price
        currency="INR",
    )
    with patch(
        "app.api.v1.endpoints.subscription.fulfill_payment",
        new_callable=AsyncMock,
    ) as mock_fulfill:
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 400
    mock_fulfill.assert_not_awaited()
    pe = _added_payment_events(db)[0]
    assert pe.status == "failed"


@pytest.mark.asyncio
async def test_webhook_captured_credit_fulfills_and_grants_welcome_gift(
    async_client, app
):
    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id=uuid.uuid4(), region="IN")
    db = _mock_db([_result(first=None), _result(first=user)])

    event = _event(
        "payment.captured",
        notes={
            "user_id": str(user.id),
            "item_type": "credit",
            "item_id": "credits_5",
        },
        amount=500,
        currency="inr",
    )
    with (
        patch(
            "app.api.v1.endpoints.subscription.validate_order_scope_and_amount",
            return_value=([], 500, "inr"),
        ),
        patch(
            "app.api.v1.endpoints.subscription.fulfill_payment",
            new_callable=AsyncMock,
        ) as mock_fulfill,
        patch(
            "app.api.v1.endpoints.subscription.maybe_grant_welcome_gift",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_gift,
    ):
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_fulfill.assert_awaited_once()
    mock_gift.assert_awaited_once()
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"


@pytest.mark.asyncio
async def test_webhook_captured_pass_with_empty_tool_ids_returns_400(async_client, app):
    """Pass fulfillment with no tool coverage must be blocked (B-4)."""
    user_id = uuid.uuid4()
    db = _mock_db([_result(first=None)])

    event = _event(
        "payment.captured",
        notes={"user_id": str(user_id), "item_type": "pass", "item_id": "quick_fix"},
        amount=200,
        currency="inr",
    )
    with patch(
        "app.api.v1.endpoints.subscription.validate_order_scope_and_amount",
        return_value=([], 200, "inr"),
    ):
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 400
    assert "tool_ids" in response.json()["detail"]
    pe = _added_payment_events(db)[0]
    assert pe.status == "failed"


@pytest.mark.asyncio
async def test_webhook_captured_unknown_item_type_acknowledged(async_client, app):
    """Unknown item_type is acknowledged (processed) without fulfillment."""
    user_id = uuid.uuid4()
    db = _mock_db([_result(first=None)])

    event = _event(
        "payment.captured",
        notes={"user_id": str(user_id), "item_type": "mystery_box"},
    )
    with patch(
        "app.api.v1.endpoints.subscription.fulfill_payment",
        new_callable=AsyncMock,
    ) as mock_fulfill:
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_fulfill.assert_not_awaited()
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"


@pytest.mark.asyncio
async def test_webhook_captured_user_not_found_returns_400(async_client, app):
    db = _mock_db([_result(first=None), _result(first=None)])

    event = _event(
        "payment.captured",
        notes={"user_id": str(uuid.uuid4()), "item_type": "pro_subscription"},
        amount=39900,
        currency="INR",
    )
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 400
    assert "user not found" in response.json()["detail"].lower()
    pe = _added_payment_events(db)[0]
    assert pe.status == "failed"


@pytest.mark.asyncio
async def test_webhook_captured_already_fulfilled_records_duplicate_audit_row(
    async_client, app
):
    """AlreadyFulfilled → 200 already_fulfilled + a status='duplicate' audit
    PaymentEvent inserted in a fresh transaction (M-3)."""
    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id=uuid.uuid4(), region="IN")
    db = _mock_db([_result(first=None), _result(first=user)])

    event = _event(
        "payment.captured",
        notes={"user_id": str(user.id), "item_type": "pro_subscription"},
        amount=39900,
        currency="INR",
    )
    with patch(
        "app.api.v1.endpoints.subscription.fulfill_payment",
        new_callable=AsyncMock,
        side_effect=AlreadyFulfilled("pay_test_1"),
    ):
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "already_fulfilled"}
    events = _added_payment_events(db)
    assert events[-1].status == "duplicate"
    db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_webhook_captured_unexpected_error_returns_500(async_client, app):
    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id=uuid.uuid4(), region="IN")
    db = _mock_db([_result(first=None), _result(first=user)])

    event = _event(
        "payment.captured",
        notes={"user_id": str(user.id), "item_type": "pro_subscription"},
        amount=39900,
        currency="INR",
    )
    with patch(
        "app.api.v1.endpoints.subscription.fulfill_payment",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db exploded"),
    ):
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 500
    assert "webhook processing failed" in response.json()["detail"].lower()
    db.rollback.assert_awaited()


# ── Subscription lifecycle events ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_subscription_cancelled_downgrades_active_sub(async_client, app):
    active_sub = SimpleNamespace(status="active", cancelled_at=None)
    db = _mock_db([_result(first=None), _result(first=active_sub)])

    event = _event("subscription.cancelled", notes={"user_id": str(uuid.uuid4())})
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert active_sub.status == "cancelled"
    assert active_sub.cancelled_at is not None
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"


@pytest.mark.asyncio
async def test_webhook_subscription_halted_pauses_active_sub(async_client, app):
    active_sub = SimpleNamespace(status="active")
    db = _mock_db([_result(first=None), _result(first=active_sub)])

    event = _event("subscription.halted", notes={"user_id": str(uuid.uuid4())})
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert active_sub.status == "halted"
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"


# ── Unhandled events ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_unhandled_event_type_acknowledged(async_client, app):
    db = _mock_db([_result(first=None)])

    event = _event("refund.created")
    response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"


# ── payment.captured - auto-refund of unfulfillable captured payments ─────────


@pytest.mark.asyncio
async def test_webhook_captured_validation_failure_auto_refunds(async_client, app):
    """A KNOWN user's captured payment failing validation (e.g. legacy scoped
    pass ordered with empty tool_ids) → refunded exactly once, event marked
    processed, 200 so Razorpay stops retrying. No grant ever happens."""
    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id=uuid.uuid4(), region="IN")
    db = _mock_db([_result(first=None)])
    db.scalar = AsyncMock(return_value=user.keycloak_id)

    event = _event(
        "payment.captured",
        # day_triple is a 3-tool pass; empty tool_ids can never be fulfilled.
        notes={
            "user_id": str(user.id),
            "item_type": "pass",
            "item_id": "day_triple",
            "tool_ids": "",
        },
        amount=2500,
        currency="INR",
    )
    with (
        patch(
            "app.api.v1.endpoints.subscription.fulfill_payment",
            new_callable=AsyncMock,
        ) as mock_fulfill,
        patch(
            "app.api.v1.endpoints.subscription.refund_unfulfillable_payment",
            new_callable=AsyncMock,
        ) as mock_refund,
    ):
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "refunded"}
    mock_fulfill.assert_not_awaited()
    mock_refund.assert_awaited_once()
    assert mock_refund.call_args.kwargs["via"] == "webhook"
    pe = _added_payment_events(db)[0]
    assert pe.status == "processed"


@pytest.mark.asyncio
async def test_webhook_captured_refund_api_failure_returns_500_for_retry(
    async_client, app
):
    """If the Razorpay refund call fails, respond non-2xx so Razorpay
    redelivers and the refund is re-attempted (ledger row was rolled back)."""
    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id=uuid.uuid4(), region="IN")
    db = _mock_db([_result(first=None)])
    db.scalar = AsyncMock(return_value=user.keycloak_id)

    event = _event(
        "payment.captured",
        notes={"user_id": str(user.id), "item_type": "pro_subscription"},
        amount=1,  # not a catalog price
        currency="INR",
    )
    with patch(
        "app.api.v1.endpoints.subscription.refund_unfulfillable_payment",
        new_callable=AsyncMock,
        side_effect=RuntimeError("razorpay down"),
    ):
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 500
    db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_webhook_captured_already_refunded_is_acknowledged(async_client, app):
    """A redelivered event for an already-refunded (or already-fulfilled)
    payment is acknowledged without a second refund."""
    from app.services.fulfillment_service import AlreadyFulfilled

    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id=uuid.uuid4(), region="IN")
    db = _mock_db([_result(first=None)])
    db.scalar = AsyncMock(return_value=user.keycloak_id)

    event = _event(
        "payment.captured",
        notes={"user_id": str(user.id), "item_type": "pro_subscription"},
        amount=1,
        currency="INR",
    )
    with patch(
        "app.api.v1.endpoints.subscription.refund_unfulfillable_payment",
        new_callable=AsyncMock,
        side_effect=AlreadyFulfilled("pay_test_1"),
    ):
        response = await _post_webhook(async_client, app, db, event)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "duplicate"}
