"""keycloak_sub denormalization correctness for billing writes.

Every billing table carries a keycloak_sub column denormalized from
auth.users.keycloak_id, and the entitlement tables (payment_fulfillments,
user_passes, user_credits, subscriptions) declare it NOT NULL. The insert
paths originally never populated it, so every real purchase 500'd at flush
with NotNullViolationError (same defect as the account-svc gamification 500).
These tests pin both halves of the fix:

  1. The service-layer writers (grant_pass, grant_credits, fulfill_payment)
     populate keycloak_sub from the User row.
  2. PaymentEvent.keycloak_sub is nullable — webhook events can reference an
     unknown user or none at all (user_id is nullable by design), so the
     audit insert must not require a subject.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _fake_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        keycloak_id=uuid.uuid4(),
        region="US",
    )


def _fake_db():
    """AsyncSession stand-in: captures db.add()ed objects, no-ops the rest."""
    db = MagicMock()
    db.added = []
    db.add = db.added.append
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=None)
    nested.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested)
    # Pro fulfillment queries for an in-period subscription first (renewal
    # extend-in-place); "no existing row" routes it to the fresh-insert path.
    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None
    empty_result.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=empty_result)
    return db


# ── Schema shape: NOT NULL where a user always exists, nullable on events ────


def test_entitlement_tables_require_keycloak_sub():
    from app.db.models.billing_credit import BillingUserCredit
    from app.db.models.billing_pass import BillingUserPass
    from app.db.models.billing_subscription import Subscription
    from app.db.models.payment_fulfillment import PaymentFulfillment

    for model in (PaymentFulfillment, BillingUserPass, BillingUserCredit, Subscription):
        col = model.__table__.c.keycloak_sub
        assert col.nullable is False, f"{model.__name__}.keycloak_sub must be NOT NULL"


def test_payment_event_keycloak_sub_is_nullable():
    """Webhook events may have no resolvable user (malformed notes, deleted
    user) — matching the nullable user_id — so the audit row must be
    insertable without a subject (migration 0002)."""
    from app.db.models.billing_subscription import PaymentEvent

    assert PaymentEvent.__table__.c.keycloak_sub.nullable is True


# ── Writer coverage: every entitlement insert carries the subject ────────────


@pytest.mark.asyncio
async def test_grant_pass_populates_keycloak_sub():
    from app.db.models.billing_pass import BillingUserPass
    from app.services.pass_service import grant_pass

    user, db = _fake_user(), _fake_db()
    billing_pass = await grant_pass(user, "quick_fix", ["uppercase"], "razorpay", db)

    assert isinstance(billing_pass, BillingUserPass)
    assert billing_pass.keycloak_sub == str(user.keycloak_id)


@pytest.mark.asyncio
async def test_grant_credits_populates_keycloak_sub():
    from app.services.pass_service import grant_credits

    user, db = _fake_user(), _fake_db()
    billing_credit = await grant_credits(user, 5, "purchase", db)

    assert billing_credit.keycloak_sub == str(user.keycloak_id)


@pytest.mark.asyncio
async def test_fulfill_payment_populates_keycloak_sub_on_ledger_and_grant():
    from app.db.models.payment_fulfillment import PaymentFulfillment
    from app.services.fulfillment_service import fulfill_payment

    user, db = _fake_user(), _fake_db()
    fulfillment = await fulfill_payment(
        db=db,
        user=user,
        razorpay_payment_id="pay_test123",
        razorpay_order_id="order_test123",
        item_type="credit",
        item_id="credits_5",
        tool_ids=[],
        amount_subunits=9900,
        currency="INR",
        fulfilled_via="verify",
    )

    assert fulfillment.keycloak_sub == str(user.keycloak_id)
    added_types = {type(o).__name__: o for o in db.added}
    assert isinstance(added_types.get("PaymentFulfillment"), PaymentFulfillment)
    assert added_types["BillingUserCredit"].keycloak_sub == str(user.keycloak_id)


@pytest.mark.asyncio
async def test_fulfill_payment_pro_subscription_populates_keycloak_sub():
    from app.services.fulfillment_service import fulfill_payment

    user, db = _fake_user(), _fake_db()
    await fulfill_payment(
        db=db,
        user=user,
        razorpay_payment_id="pay_test456",
        razorpay_order_id="order_test456",
        item_type="pro_subscription",
        item_id=None,
        tool_ids=[],
        amount_subunits=49900,
        currency="INR",
        fulfilled_via="webhook",
    )

    subscription = next(o for o in db.added if type(o).__name__ == "Subscription")
    assert subscription.keycloak_sub == str(user.keycloak_id)
