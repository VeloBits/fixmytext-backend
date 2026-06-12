"""Single payment-fulfillment authority — exactly-once grants via a ledger.

Both the synchronous client callbacks (``/passes/verify``, ``/subscription/verify``)
and the asynchronous ``payment.captured`` webhook call :func:`fulfill_payment`.
It inserts a ``payment_fulfillments`` row keyed by the Razorpay payment id inside
a SAVEPOINT *before* granting anything; the UNIQUE index means the second
concurrent writer (verify-vs-webhook race) or a replayed payment trips an
``IntegrityError``, surfaced as :class:`AlreadyFulfilled`, so the entitlement is
granted exactly once. Fixes C-1 (replay) and H-2 (double-grant).
"""

import logging

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pass_catalog import get_credit_pack
from app.db.models.billing_subscription import Subscription
from app.db.models.payment_fulfillment import PaymentFulfillment
from app.db.models.user import User
from app.services.pass_service import grant_credits, grant_pass

logger = logging.getLogger(__name__)


class AlreadyFulfilled(Exception):
    """Raised when a Razorpay payment id already has a fulfillment row.

    Callers treat this as the idempotent-success path: roll back the current
    transaction (no second grant) and return the same success response the
    original fulfillment returned.
    """

    def __init__(self, razorpay_payment_id: str):
        self.razorpay_payment_id = razorpay_payment_id
        super().__init__(f"Payment already fulfilled: {razorpay_payment_id}")


async def fulfill_payment(
    *,
    db: AsyncSession,
    user: User,
    razorpay_payment_id: str,
    razorpay_order_id: str | None,
    item_type: str,
    item_id: str | None,
    tool_ids: list[str],
    amount_subunits: int | None,
    currency: str | None,
    fulfilled_via: str,
) -> PaymentFulfillment:
    """Grant the purchased entitlement exactly once for *razorpay_payment_id*.

    The caller owns the surrounding transaction and is responsible for the final
    ``commit()`` (on success) or ``rollback()`` (on :class:`AlreadyFulfilled` or
    any other error). The caller must have already validated the order
    amount/scope (see :mod:`app.services.order_validation`) and should hold a row
    lock on the user where welcome-gift atomicity matters.

    Raises:
        AlreadyFulfilled: this payment id was already fulfilled (replay/race).
        HTTPException: unknown/invalid item — should not occur post-validation.
    """
    fulfillment = PaymentFulfillment(
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
        user_id=user.id,
        item_type=item_type,
        item_id=item_id,
        amount_subunits=amount_subunits,
        currency=currency,
        fulfilled_via=fulfilled_via,
        status="pending",
    )
    # Insert the ledger row first, inside a SAVEPOINT. A concurrent writer or a
    # replay with the same payment id trips the UNIQUE index here; we convert the
    # IntegrityError to AlreadyFulfilled and the savepoint rolls back, leaving the
    # outer transaction (and any user-row lock) intact for the caller.
    try:
        async with db.begin_nested():
            db.add(fulfillment)
            await db.flush()
    except IntegrityError as exc:
        raise AlreadyFulfilled(razorpay_payment_id) from exc

    if item_type == "pass":
        if item_id is None:
            raise HTTPException(400, "Missing pass id")
        billing_pass = await grant_pass(
            user,
            item_id,
            tool_ids,
            "razorpay",
            db,
            razorpay_payment_id=razorpay_payment_id,
            auto_commit=False,
        )
        fulfillment.result_ref = {"pass_instance_id": str(billing_pass.id)}

    elif item_type == "credit":
        pack = get_credit_pack(item_id) if item_id else None
        if not pack:
            raise HTTPException(400, f"Unknown credit pack: {item_id}")
        billing_credit = await grant_credits(
            user,
            pack["credits"],
            "purchase",
            db,
            razorpay_payment_id=razorpay_payment_id,
            auto_commit=False,
        )
        await db.flush()  # populate the server-generated id for result_ref
        fulfillment.result_ref = {"credit_id": str(billing_credit.id)}

    elif item_type == "pro_subscription":
        subscription = Subscription(
            user_id=user.id,
            tier="pro",
            status="active",
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            amount_paid_subunits=amount_subunits,
            currency=currency,
            region=user.region,
        )
        # The one-active-subscription partial unique index guards this insert; a
        # pre-existing active sub (a legacy row without a ledger entry, or a
        # race) surfaces as AlreadyFulfilled so callers stay idempotent.
        try:
            async with db.begin_nested():
                db.add(subscription)
                await db.flush()
        except IntegrityError as exc:
            raise AlreadyFulfilled(razorpay_payment_id) from exc
        fulfillment.result_ref = {"subscription_id": str(subscription.id)}

    else:
        raise HTTPException(400, f"Unknown item_type: {item_type}")

    fulfillment.status = "fulfilled"
    return fulfillment
