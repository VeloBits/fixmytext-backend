"""Unit tests for fulfillment_service: Pro expiry/renewal and auto-refunds.

Mocked-session twins of the real-DB tests in test_fulfillment.py - these run
without TEST_DATABASE_URL and pin the branch logic:

  * a fresh Pro purchase stamps expires_at = now + PRO_DURATION_DAYS,
  * renewing an in-period plan extends IN PLACE from max(now, old expiry)
    (no new row → never trips the one-active-sub unique index),
  * renewing a cancelled-in-period plan reactivates it,
  * refund_unfulfillable_payment issues exactly one refund per payment id and
    rolls back cleanly when the Razorpay call fails.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.services.fulfillment_service import (
    AlreadyFulfilled,
    fulfill_payment,
    refund_unfulfillable_payment,
)


def _fake_user():
    return SimpleNamespace(id=uuid.uuid4(), keycloak_id=uuid.uuid4(), region="IN")


def _fake_db(existing_sub=None):
    """AsyncSession stand-in. `existing_sub` is what the pro-renewal lookup
    returns; update()/select() calls resolve to the same mock result."""
    db = MagicMock()
    db.added = []
    db.add = db.added.append
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=None)
    nested.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested)
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_sub
    result.scalars.return_value.first.return_value = existing_sub
    db.execute = AsyncMock(return_value=result)
    return db


def _pro_kwargs(user, db, payment_id="pay_pro_1"):
    return {
        "db": db,
        "user": user,
        "razorpay_payment_id": payment_id,
        "razorpay_order_id": "order_pro_1",
        "item_type": "pro_subscription",
        "item_id": None,
        "tool_ids": [],
        "amount_subunits": 39900,
        "currency": "INR",
        "fulfilled_via": "verify",
    }


# ── Pro expiry stamping ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fresh_pro_purchase_stamps_30_day_expiry():
    user, db = _fake_user(), _fake_db(existing_sub=None)

    fulfillment = await fulfill_payment(**_pro_kwargs(user, db))

    sub = next(o for o in db.added if type(o).__name__ == "Subscription")
    remaining = sub.expires_at - datetime.now(UTC)
    assert (
        timedelta(days=settings.PRO_DURATION_DAYS) - timedelta(minutes=1)
        < remaining
        <= timedelta(days=settings.PRO_DURATION_DAYS)
    )
    assert sub.status == "active"
    assert fulfillment.status == "fulfilled"


@pytest.mark.asyncio
async def test_renewal_extends_in_place_from_current_expiry():
    """Early renewal never loses paid days: new expiry = old expiry + 30d,
    and the existing row is updated (no insert → no unique-index conflict)."""
    old_expiry = datetime.now(UTC) + timedelta(days=5)
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        status="active",
        expires_at=old_expiry,
        cancelled_at=None,
        razorpay_order_id="order_old",
        razorpay_payment_id="pay_old",
        amount_paid_subunits=39900,
        currency="INR",
    )
    user, db = _fake_user(), _fake_db(existing_sub=existing)

    fulfillment = await fulfill_payment(**_pro_kwargs(user, db, "pay_pro_2"))

    assert existing.expires_at == old_expiry + timedelta(
        days=settings.PRO_DURATION_DAYS
    )
    assert existing.status == "active"
    assert existing.razorpay_payment_id == "pay_pro_2"
    assert fulfillment.result_ref["renewal"] is True
    # No new Subscription row was inserted.
    assert not [o for o in db.added if type(o).__name__ == "Subscription"]


@pytest.mark.asyncio
async def test_renewal_reactivates_cancelled_in_period_plan():
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        status="cancelled",
        expires_at=datetime.now(UTC) + timedelta(days=3),
        cancelled_at=datetime.now(UTC) - timedelta(days=1),
        razorpay_order_id="order_old",
        razorpay_payment_id="pay_old",
        amount_paid_subunits=39900,
        currency="INR",
    )
    user, db = _fake_user(), _fake_db(existing_sub=existing)

    await fulfill_payment(**_pro_kwargs(user, db, "pay_pro_3"))

    assert existing.status == "active"
    assert existing.cancelled_at is None


# ── refund_unfulfillable_payment ──────────────────────────────────────────────


def _refund_kwargs(db, payment_id="pay_bad_1"):
    return {
        "db": db,
        "user_id": uuid.uuid4(),
        "keycloak_sub": str(uuid.uuid4()),
        "razorpay_payment_id": payment_id,
        "razorpay_order_id": "order_bad_1",
        "item_type": "pass",
        "item_id": "day_triple",
        "amount_subunits": 2500,
        "currency": "INR",
        "via": "verify",
        "reason": "tool_ids count does not match the purchased pass",
    }


@pytest.mark.asyncio
async def test_refund_records_ledger_row_and_calls_razorpay():
    db = _fake_db()
    with patch(
        "app.services.fulfillment_service.refund_payment",
        return_value={"id": "rfnd_1", "status": "processed"},
    ) as mock_refund:
        fulfillment = await refund_unfulfillable_payment(**_refund_kwargs(db))

    mock_refund.assert_called_once()
    assert fulfillment.status == "refunded"
    assert fulfillment.result_ref["refund_id"] == "rfnd_1"
    assert fulfillment in db.added


@pytest.mark.asyncio
async def test_refund_is_exactly_once_via_unique_payment_id():
    """A second attempt for the same payment id (already refunded OR already
    fulfilled) trips the UNIQUE ledger index → AlreadyFulfilled, and the
    Razorpay refund API is never called again."""
    db = _fake_db()
    db.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    with (
        patch("app.services.fulfillment_service.refund_payment") as mock_refund,
        pytest.raises(AlreadyFulfilled),
    ):
        await refund_unfulfillable_payment(**_refund_kwargs(db))

    mock_refund.assert_not_called()


@pytest.mark.asyncio
async def test_refund_api_failure_propagates_for_retry():
    """A Razorpay failure re-raises so the caller rolls back the ledger row
    and Razorpay's webhook retry re-attempts the refund safely."""
    db = _fake_db()
    with (
        patch(
            "app.services.fulfillment_service.refund_payment",
            side_effect=RuntimeError("razorpay down"),
        ),
        pytest.raises(RuntimeError),
    ):
        await refund_unfulfillable_payment(**_refund_kwargs(db))
