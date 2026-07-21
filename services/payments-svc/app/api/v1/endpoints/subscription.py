"""Subscription endpoints: status, checkout (Pro), verify, cancel, webhook."""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models.billing_subscription import PaymentEvent, Subscription
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.subscription import (
    RazorpayProOrderResponse,
    RazorpayProVerifyRequest,
    SubscriptionStatus,
)
from app.services.fulfillment_service import (
    AlreadyFulfilled,
    fulfill_payment,
    refund_unfulfillable_payment,
)
from app.services.order_validation import (
    validate_order_scope_and_amount,
    validate_pro_amount,
)
from app.services.pass_service import (
    get_active_passes,
    get_all_tool_uses_today,
    get_credit_balance,
    get_pro_subscription,
    has_logged_in_today,
    maybe_grant_welcome_gift,
    record_daily_login,
)
from app.services.rate_limit import check_rate_limit
from app.services.razorpay_service import (
    PRO_PLAN_PRICES,
    create_order,
    fetch_order,
    payments_configured,
    verify_payment_signature,
    verify_webhook_signature,
)
from app.services.region_service import resolve_user_region

logger = logging.getLogger(__name__)


def _s(value: str | None) -> str:
    """Sanitize a string value for safe logging."""
    if value is None:
        return ""
    return str(value).replace("\n", "").replace("\r", "")


router = APIRouter(prefix="/subscription", tags=["Subscription"])


# ── Status ────────────────────────────────────────────────────────────


@router.get("/status", response_model=SubscriptionStatus)
async def subscription_status(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's subscription status, usage, and pass/credit info."""

    if not user.region:
        await resolve_user_region(user, request, db)
        await db.commit()

    tool_uses = await get_all_tool_uses_today(user.id, db)

    daily_bonus = await has_logged_in_today(user.id, db)
    if not daily_bonus:
        await record_daily_login(user, db)
        daily_bonus = True

    credit_balance = await get_credit_balance(user, db)
    active_passes = await get_active_passes(user, db)
    pro_sub = await get_pro_subscription(user.id, db)

    return SubscriptionStatus(
        tier="pro" if pro_sub else "free",
        tool_uses_today=tool_uses,
        free_uses_per_tool=settings.FREE_USES_PER_TOOL_PER_DAY,
        daily_login_bonus=daily_bonus,
        credit_balance=credit_balance,
        active_passes_count=len(active_passes),
        region=user.region,
        pro_expires_at=pro_sub.expires_at if pro_sub else None,
        pro_cancelled=bool(pro_sub and pro_sub.status == "cancelled"),
    )


# ── Pro Checkout (create Razorpay order — one-time payment) ─────────────────


@router.post("/checkout", response_model=RazorpayProOrderResponse)
async def create_pro_checkout(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Razorpay order for upgrading to Pro (one-time monthly payment)."""
    if not payments_configured():
        raise HTTPException(503, "Payments not configured")
    await check_rate_limit(
        f"ratelimit:order:{user.id}", settings.ORDER_RATE_LIMIT_PER_MINUTE
    )

    # Renewal window: an ACTIVE Pro can re-purchase only within the last
    # PRO_RENEWAL_WINDOW_DAYS of the period (fulfillment extends from the
    # current expiry, so early renewal never loses paid days). A cancelled
    # in-period Pro can re-subscribe any time — that reactivates the plan.
    pro_sub = await get_pro_subscription(user.id, db)
    if pro_sub and pro_sub.status == "active":
        window = timedelta(days=settings.PRO_RENEWAL_WINDOW_DAYS)
        if pro_sub.expires_at - datetime.now(UTC) > window:
            expiry = pro_sub.expires_at.date().isoformat()
            raise HTTPException(
                400,
                f"You're subscribed until {expiry}. Renewal opens "
                f"{settings.PRO_RENEWAL_WINDOW_DAYS} days before expiry.",
            )

    region = user.region or "IN"
    pricing = PRO_PLAN_PRICES.get(region, PRO_PLAN_PRICES["IN"])

    # Short enough to survive Razorpay's 40-char receipt cap untruncated.
    idempotency_key = f"pro_{user.id.hex[:8]}"

    try:
        order = create_order(
            amount=pricing["amount"],
            currency=pricing["currency"],
            receipt=idempotency_key,
            notes={"user_id": str(user.id), "item_type": "pro_subscription"},
            idempotency_key=idempotency_key,
        )
    except Exception as e:
        logger.exception(
            "Failed to create Razorpay order for Pro checkout, user %s", user.id
        )
        raise HTTPException(
            502, "Failed to start checkout — please try again later"
        ) from e

    return RazorpayProOrderResponse(
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
        key_id=settings.RAZORPAY_KEY_ID,
        user_email=user.email,
        user_name=user.display_name,
    )


# ── Verify Pro Payment ────────────────────────────────────────────────


@router.post("/verify")
async def verify_pro_payment(
    req: RazorpayProVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify Razorpay payment and activate Pro.

    Trust model:
      1. The client-supplied signature is verified against Razorpay's servers.
      2. The order is re-fetched from Razorpay's API (server-to-server) and the
         ``notes.user_id`` embedded at order-creation time is compared to the
         authenticated user.  These notes originate from *our* backend (set in
         ``create_pro_checkout``), not from the client request, so they are
         trustworthy once the order ID is confirmed authentic.
    """
    if not verify_payment_signature(
        req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature
    ):
        raise HTTPException(400, "Payment verification failed — invalid signature")

    # Re-fetch the order server-to-server so we read notes set by *our* backend
    # at creation time — not user-supplied data.
    try:
        order = fetch_order(req.razorpay_order_id)
    except Exception as e:
        logger.exception("Failed to fetch order %s", _s(req.razorpay_order_id))
        raise HTTPException(502, "Could not verify order details") from e

    notes = order.get("notes", {})
    if notes.get("user_id") != str(user.id):
        raise HTTPException(400, "Order does not belong to this user")
    if notes.get("item_type") != "pro_subscription":
        raise HTTPException(400, "Order is not for Pro subscription")

    # Block amount tampering, then fulfill exactly once through the shared
    # authority — a double verify or a verify/webhook race activates Pro once.
    # The signature above is VALID, so an amount-validation failure means a
    # real customer paid for an order we cannot fulfil — auto-refund it.
    try:
        validate_pro_amount(order.get("amount"), order.get("currency"))
    except HTTPException as validation_error:
        try:
            await refund_unfulfillable_payment(
                db=db,
                user_id=user.id,
                keycloak_sub=str(user.keycloak_id),
                razorpay_payment_id=req.razorpay_payment_id,
                razorpay_order_id=req.razorpay_order_id,
                item_type="pro_subscription",
                item_id=None,
                amount_subunits=order.get("amount"),
                currency=order.get("currency"),
                via="verify",
                reason=str(validation_error.detail),
            )
            await db.commit()
        except AlreadyFulfilled:
            await db.rollback()
            return {"status": "success", "detail": "already_fulfilled"}
        except Exception:
            await db.rollback()
            logger.exception(
                "Refund attempt failed (pro verify): payment=%s",
                _s(req.razorpay_payment_id),
            )
            raise HTTPException(
                502, "Could not refund the payment — please contact support"
            ) from validation_error
        return {
            "status": "refunded",
            "detail": "order_validation_failed",
            "message": "Your payment was refunded because the order could not be "
            "validated. The amount should reach your account in 5-7 business days.",
        }

    await db.execute(select(User).where(User.id == user.id).with_for_update())

    welcome = False
    try:
        await fulfill_payment(
            db=db,
            user=user,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_order_id=req.razorpay_order_id,
            item_type="pro_subscription",
            item_id=None,
            tool_ids=[],
            amount_subunits=order.get("amount"),
            currency=order.get("currency"),
            fulfilled_via="verify",
        )
        # First-purchase welcome gift: a first-ever purchase that happens to be
        # Pro earns the same one-time bonus as a pass/credit first purchase.
        welcome = await maybe_grant_welcome_gift(user, db)
        if welcome:
            logger.info("Welcome gift granted (pro): user=%s", user.id)
        await db.commit()
    except (AlreadyFulfilled, IntegrityError):
        # Already fulfilled (replay) or an active subscription already exists —
        # idempotent success instead of a 500 on the one-active-sub constraint.
        await db.rollback()
        logger.info(
            "Pro already active (verify): user=%s payment=%s",
            user.id,
            _s(req.razorpay_payment_id),
        )
        return {"status": "success", "tier": "pro", "detail": "already_fulfilled"}
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "Pro activated: user=%s order=%s payment=%s",
        user.id,
        _s(req.razorpay_order_id),
        _s(req.razorpay_payment_id),
    )
    return {
        "status": "success",
        "tier": "pro",
        "welcome_gift": welcome,
        "welcome_credits": settings.WELCOME_GIFT_CREDITS if welcome else 0,
    }


# ── Cancel Pro ────────────────────────────────────────────────────────


@router.post("/cancel")
async def cancel_pro(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel Pro. Access continues until the paid period ends (expires_at).

    Idempotent: cancelling an already-cancelled in-period plan returns the
    same response without changing anything.
    """
    pro_sub = await get_pro_subscription(user.id, db)
    if not pro_sub:
        raise HTTPException(400, "No active Pro subscription")

    if pro_sub.status == "active":
        pro_sub.status = "cancelled"
        pro_sub.cancelled_at = datetime.now(UTC)
        await db.commit()

    return {
        "status": "cancelled",
        "access_until": pro_sub.expires_at.isoformat() if pro_sub.expires_at else None,
    }


# ── Webhook ───────────────────────────────────────────────────────────


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):  # noqa: C901
    """Handle Razorpay webhook events for payments.

    Supports: payment.captured, payment.authorized, payment.failed,
    subscription.cancelled, subscription.halted.

    Idempotent — duplicate events (same razorpay_event_id) are acknowledged
    but not reprocessed.
    """
    # Reject oversized payloads before reading — protects against memory exhaustion.
    _cl = request.headers.get("content-length")
    if _cl:
        try:
            if int(_cl) > settings.WEBHOOK_MAX_BODY_BYTES:
                raise HTTPException(413, "Webhook payload too large")
        except ValueError:
            raise HTTPException(413, "Webhook payload too large") from None
    body = await request.body()
    if len(body) > settings.WEBHOOK_MAX_BODY_BYTES:
        raise HTTPException(413, "Webhook payload too large")
    signature = request.headers.get("x-razorpay-signature", "")

    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook secret not configured")
    if not verify_webhook_signature(body, signature):
        raise HTTPException(400, "Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(400, "Invalid payload") from e

    event_type = event.get("event", "")
    # Prefer the authoritative Razorpay event ID; fall back to composite key
    # for older webhook formats that may not include the top-level "id" field.
    razorpay_event_id = event.get("id") or (
        event.get("account_id", "") + "_" + str(event.get("created_at", ""))
    )
    payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
    payment_id = payment_entity.get("id")
    order_id = payment_entity.get("order_id")
    amount = payment_entity.get("amount")
    currency = payment_entity.get("currency")
    notes = payment_entity.get("notes", {})

    user_id_str = notes.get("user_id")
    item_type = notes.get("item_type")
    item_id = notes.get("item_id")

    # Log-safe versions — inline .replace() so static analysis (CodeQL) can
    # verify the taint is removed before values reach logging sinks.
    safe_event_type = str(event_type).replace("\n", "").replace("\r", "")
    safe_event_id = str(razorpay_event_id).replace("\n", "").replace("\r", "")
    safe_payment_id = str(payment_id).replace("\n", "").replace("\r", "")
    safe_order_id = str(order_id).replace("\n", "").replace("\r", "")
    safe_item_type = str(item_type).replace("\n", "").replace("\r", "")
    safe_item_id = str(item_id).replace("\n", "").replace("\r", "")

    # ── Idempotency check — skip already-processed events ────────────
    existing = await db.execute(
        select(PaymentEvent).where(
            PaymentEvent.razorpay_event_id == razorpay_event_id,
            PaymentEvent.status == "processed",
        )
    )
    if existing.scalars().first():
        logger.info("Duplicate webhook ignored: event_id=%s", safe_event_id)
        return {"status": "ok", "detail": "duplicate"}

    # ── Parse user_id safely — malformed values must not cause a 500 ──
    user_id = None
    if user_id_str:
        try:
            user_id = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            pe = PaymentEvent(
                event_type=event_type,
                razorpay_event_id=razorpay_event_id,
                razorpay_payment_id=payment_id,
                razorpay_order_id=order_id,
                user_id=None,
                keycloak_sub=None,
                item_type=item_type,
                item_id=item_id,
                amount_subunits=amount,
                currency=currency,
                status="failed",
                raw_payload=event,
            )
            db.add(pe)
            await db.flush()
            await db.commit()
            raise HTTPException(
                status_code=400, detail="Invalid user_id in webhook notes"
            ) from None

    # Denormalized Keycloak subject for audit rows. Events can reference an
    # unknown user (or none at all), so this may legitimately stay None.
    keycloak_id = None
    if user_id:
        keycloak_id = await db.scalar(
            select(User.keycloak_id).where(User.id == user_id)
        )
    keycloak_sub = str(keycloak_id) if keycloak_id else None

    # ── Record the event ─────────────────────────────────────────────
    pe = PaymentEvent(
        event_type=event_type,
        razorpay_event_id=razorpay_event_id,
        razorpay_payment_id=payment_id,
        razorpay_order_id=order_id,
        user_id=user_id,
        keycloak_sub=keycloak_sub,
        item_type=item_type,
        item_id=item_id,
        amount_subunits=amount,
        currency=currency,
        status="received",
        raw_payload=event,
    )
    db.add(pe)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent delivery of the same razorpay_event_id raced us to the
        # unique index — treat as a duplicate rather than 500 (BE-DATA-06). The
        # winning delivery fulfills it, and the payment_fulfillments ledger
        # guarantees the grant happens exactly once regardless.
        await db.rollback()
        logger.info(
            "Duplicate webhook (concurrent insert) ignored: event_id=%s", safe_event_id
        )
        return {"status": "ok", "detail": "duplicate"}

    # ── payment.authorized — informational only (capture pending) ────
    if event_type == "payment.authorized":
        logger.info(
            "payment.authorized: payment=%s order=%s",
            safe_payment_id,
            safe_order_id,
        )
        pe.status = "processed"
        pe.processed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "ok"}

    # ── payment.failed — log failure ─────────────────────────────────
    if event_type == "payment.failed":
        reason = (
            str(payment_entity.get("error_description", "unknown"))
            .replace("\n", "")
            .replace("\r", "")
        )
        logger.warning(
            "payment.failed: payment=%s order=%s reason=%s",
            safe_payment_id,
            safe_order_id,
            reason,
        )
        pe.status = "processed"
        pe.processed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "ok"}

    # ── payment.captured — fulfill the purchase (idempotent) ─────────
    if event_type == "payment.captured":
        if not user_id:
            logger.error(
                "payment.captured missing user_id in notes: order=%s", safe_order_id
            )
            pe.status = "failed"
            await db.commit()
            raise HTTPException(400, "Missing user_id in order notes")

        # Validate amount/scope BEFORE granting; a mismatch now BLOCKS
        # fulfillment (BE-PAY-03) and records a 'failed' event for audit.
        tool_ids: list[str] = []
        try:
            if item_type == "pro_subscription":
                validate_pro_amount(amount, currency)
            elif item_type in ("pass", "credit"):
                tool_ids, _, _ = validate_order_scope_and_amount(
                    order={"notes": notes, "amount": amount, "currency": currency},
                    expected_item_id=item_id,
                    expected_item_type=item_type,
                )
                if item_type == "pass" and not tool_ids:
                    logger.error(
                        "Webhook: pass fulfillment with empty tool_ids, aborting: order=%s",
                        safe_order_id,
                    )
                    raise HTTPException(
                        400, "Invalid order notes: missing tool_ids for pass"
                    )
            else:
                logger.warning(
                    "Unknown item_type in webhook: %s order=%s",
                    safe_item_type,
                    safe_order_id,
                )
                pe.status = "processed"
                pe.processed_at = datetime.now(UTC)
                await db.commit()
                return {"status": "ok"}
        except HTTPException as validation_error:
            # The webhook signature is VALID and the payment is CAPTURED, so a
            # validation failure here is real customer money we cannot fulfil
            # (e.g. a legacy scoped-pass order with empty tool_ids) —
            # auto-refund exactly once and acknowledge with 200 so Razorpay
            # stops retrying. A refund-API failure rolls everything back and
            # re-raises → non-2xx → Razorpay redelivers → refund re-attempted.
            if keycloak_sub is None:
                # Unknown user: no fulfillment row possible (FK); keep the
                # old failed-event behavior for the audit trail.
                pe.status = "failed"
                await db.commit()
                raise
            try:
                await refund_unfulfillable_payment(
                    db=db,
                    user_id=user_id,
                    keycloak_sub=keycloak_sub,
                    razorpay_payment_id=payment_id,
                    razorpay_order_id=order_id,
                    item_type=item_type,
                    item_id=item_id,
                    amount_subunits=amount,
                    currency=currency,
                    via="webhook",
                    reason=str(validation_error.detail),
                )
                pe.status = "processed"
                pe.processed_at = datetime.now(UTC)
                await db.commit()
                return {"status": "ok", "detail": "refunded"}
            except AlreadyFulfilled:
                # Already fulfilled or already refunded — acknowledge without
                # a second refund; commit the event row for the audit trail.
                pe.status = "processed"
                pe.processed_at = datetime.now(UTC)
                await db.commit()
                return {"status": "ok", "detail": "duplicate"}
            except Exception as refund_error:
                await db.rollback()
                logger.exception(
                    "Refund attempt failed (webhook): payment=%s", safe_payment_id
                )
                raise HTTPException(
                    500, "Refund attempt failed — Razorpay will retry"
                ) from refund_error

        try:
            # Lock + load the user for welcome-gift atomicity vs the verify path.
            user_result = await db.execute(
                select(User).where(User.id == user_id).with_for_update()
            )
            user = user_result.scalars().first()
            if not user:
                logger.error("Webhook user not found: user_id=%s", user_id)
                pe.status = "failed"
                await db.commit()
                raise HTTPException(400, "User not found")

            await fulfill_payment(
                db=db,
                user=user,
                razorpay_payment_id=payment_id,
                razorpay_order_id=order_id,
                item_type=item_type,
                item_id=item_id,
                tool_ids=tool_ids,
                amount_subunits=amount,
                currency=currency,
                fulfilled_via="webhook",
            )
            if item_type in ("pass", "credit", "pro_subscription"):
                await maybe_grant_welcome_gift(user, db)

            pe.status = "processed"
            pe.processed_at = datetime.now(UTC)
            await db.commit()
            logger.info(
                "Payment fulfilled via webhook: user=%s type=%s item=%s payment=%s",
                user.id,
                safe_item_type,
                safe_item_id,
                safe_payment_id,
            )

        except AlreadyFulfilled:
            # The verify callback (or another delivery) already fulfilled this
            # payment — acknowledge without a second grant.
            await db.rollback()
            logger.info(
                "Duplicate payment fulfillment ignored (webhook): payment=%s",
                safe_payment_id,
            )
            # The 'received' pe was rolled back; insert a 'duplicate' row in a
            # new transaction so the audit trail shows this late delivery arrived.
            try:
                dup_pe = PaymentEvent(
                    event_type=event_type,
                    razorpay_event_id=razorpay_event_id,
                    razorpay_payment_id=payment_id,
                    razorpay_order_id=order_id,
                    user_id=user_id,
                    keycloak_sub=keycloak_sub,
                    item_type=item_type,
                    item_id=item_id,
                    amount_subunits=amount,
                    currency=currency,
                    status="duplicate",
                    raw_payload=event,
                )
                db.add(dup_pe)
                await db.commit()
            except Exception:
                await db.rollback()
                logger.warning(
                    "Could not record duplicate webhook audit event: payment=%s",
                    safe_payment_id,
                )
            return {"status": "ok", "detail": "already_fulfilled"}
        except HTTPException:
            raise
        except Exception:
            await db.rollback()
            logger.exception(
                "Failed to process payment.captured: order=%s payment=%s",
                safe_order_id,
                safe_payment_id,
            )
            raise HTTPException(500, "Webhook processing failed") from None

        return {"status": "ok"}

    # ── subscription.cancelled — downgrade user ──────────────────────
    if event_type == "subscription.cancelled" and user_id:
        sub_result = await db.execute(
            select(Subscription).where(
                and_(
                    Subscription.user_id == user_id,
                    Subscription.status == "active",
                    Subscription.tier == "pro",
                )
            )
        )
        active_sub = sub_result.scalars().first()
        if active_sub:
            active_sub.status = "cancelled"
            active_sub.cancelled_at = datetime.now(UTC)
            logger.info("Subscription cancelled via webhook: user=%s", user_id)
        pe.status = "processed"
        pe.processed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "ok"}

    # ── subscription.halted — pause access ───────────────────────────
    if event_type == "subscription.halted" and user_id:
        sub_result = await db.execute(
            select(Subscription).where(
                and_(
                    Subscription.user_id == user_id,
                    Subscription.status == "active",
                    Subscription.tier == "pro",
                )
            )
        )
        active_sub = sub_result.scalars().first()
        if active_sub:
            active_sub.status = "halted"
            logger.info("Subscription halted via webhook: user=%s", user_id)
        pe.status = "processed"
        pe.processed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "ok"}

    # ── Unhandled event types — acknowledge but don't process ────────
    logger.info("Unhandled webhook event: %s", safe_event_type)
    pe.status = "processed"
    pe.processed_at = datetime.now(UTC)
    await db.commit()
    return {"status": "ok"}
