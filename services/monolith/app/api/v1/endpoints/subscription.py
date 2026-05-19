"""Subscription endpoints: status, checkout (Pro), verify, cancel, webhook."""

import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.pass_catalog import get_credit_pack, get_pass, get_price
from app.core.sanitize import sanitize_log_value as _s
from app.db.models import User
from app.db.models.billing_subscription import PaymentEvent, Subscription
from app.db.session import get_db
from app.schemas.subscription import (
    RazorpayProOrderResponse,
    RazorpayProVerifyRequest,
    SubscriptionStatus,
)
from app.services.pass_service import (
    get_active_passes,
    get_all_tool_uses_today,
    get_credit_balance,
    get_subscription_tier,
    grant_credits,
    grant_pass,
    has_logged_in_today,
    record_daily_login,
)
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

    return SubscriptionStatus(
        tier=await get_subscription_tier(user.id, db),
        tool_uses_today=tool_uses,
        free_uses_per_tool=settings.FREE_USES_PER_TOOL_PER_DAY,
        daily_login_bonus=daily_bonus,
        credit_balance=credit_balance,
        active_passes_count=len(active_passes),
        region=user.region,
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

    if await get_subscription_tier(user.id, db) == "pro":
        raise HTTPException(400, "Already subscribed to Pro")

    region = user.region or "IN"
    pricing = PRO_PLAN_PRICES.get(region, PRO_PLAN_PRICES["IN"])

    idempotency_key = f"pro_{user.id}"

    try:
        order = create_order(
            amount=pricing["amount"],
            currency=pricing["currency"],
            receipt=f"pro_{str(user.id)[:8]}",
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
        logger.exception("Failed to fetch order %s", req.razorpay_order_id)
        raise HTTPException(502, "Could not verify order details") from e

    notes = order.get("notes", {})
    if notes.get("user_id") != str(user.id):
        raise HTTPException(400, "Order does not belong to this user")
    if notes.get("item_type") != "pro_subscription":
        raise HTTPException(400, "Order is not for Pro subscription")

    # Create/update Subscription row in billing schema
    sub = Subscription(
        user_id=user.id,
        tier="pro",
        status="active",
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
        amount_paid_subunits=order.get("amount"),
        currency=order.get("currency"),
        region=user.region,
    )
    db.add(sub)

    await db.commit()
    logger.info(
        "Pro activated: user=%s order=%s payment=%s",
        user.id,
        _s(req.razorpay_order_id),
        _s(req.razorpay_payment_id),
    )
    return {"status": "success", "tier": "pro"}


# ── Cancel Pro ────────────────────────────────────────────────────────


@router.post("/cancel")
async def cancel_pro(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel Pro subscription (immediate downgrade)."""
    tier = await get_subscription_tier(user.id, db)
    if tier != "pro":
        raise HTTPException(400, "No active Pro subscription")

    # Update Subscription row
    sub_result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.user_id == user.id,
                Subscription.status == "active",
                Subscription.tier == "pro",
            )
        )
    )
    active_sub = sub_result.scalars().first()
    if active_sub:
        active_sub.status = "cancelled"
        active_sub.cancelled_at = datetime.now(UTC)

    await db.commit()
    return {"status": "cancelled"}


# ── Webhook ───────────────────────────────────────────────────────────


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Razorpay webhook events for payments.

    Supports: payment.captured, payment.authorized, payment.failed,
    subscription.cancelled, subscription.halted.

    Idempotent — duplicate events (same razorpay_event_id) are acknowledged
    but not reprocessed.
    """
    body = await request.body()
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
                item_type=item_type,
                item_id=item_id,
                amount_subunits=amount,
                currency=currency,
                status="error",
                raw_payload=event,
            )
            db.add(pe)
            await db.flush()
            await db.commit()
            raise HTTPException(
                status_code=400, detail="Invalid user_id in webhook notes"
            ) from None

    # ── Record the event ─────────────────────────────────────────────
    pe = PaymentEvent(
        event_type=event_type,
        razorpay_event_id=razorpay_event_id,
        razorpay_payment_id=payment_id,
        razorpay_order_id=order_id,
        user_id=user_id,
        item_type=item_type,
        item_id=item_id,
        amount_subunits=amount,
        currency=currency,
        status="received",
        raw_payload=event,
    )
    db.add(pe)
    await db.flush()

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

    # ── payment.captured — fulfill the purchase ──────────────────────
    if event_type == "payment.captured":
        if not user_id:
            logger.error(
                "payment.captured missing user_id in notes: order=%s", safe_order_id
            )
            pe.status = "error"
            await db.commit()
            raise HTTPException(400, "Missing user_id in order notes")

        # Validate amount matches expected catalog price
        _validate_payment_amount(
            item_type, item_id, amount, currency, user_id, order_id
        )

        try:
            # Look up user
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalars().first()
            if not user:
                logger.error("Webhook user not found: user_id=%s", user_id)
                pe.status = "error"
                await db.commit()
                raise HTTPException(400, "User not found")

            if item_type == "pro_subscription":
                sub = Subscription(
                    user_id=user.id,
                    tier="pro",
                    status="active",
                    razorpay_order_id=order_id,
                    razorpay_payment_id=payment_id,
                    amount_paid_subunits=amount,
                    currency=currency,
                    region=user.region,
                )
                db.add(sub)
                logger.info(
                    "Pro activated via webhook: user=%s payment=%s",
                    user.id,
                    safe_payment_id,
                )

            elif item_type == "pass":
                pass_def = get_pass(item_id)
                if not pass_def:
                    logger.error("Unknown pass in webhook: %s", safe_item_id)
                    pe.status = "error"
                    await db.commit()
                    raise HTTPException(400, f"Unknown pass: {item_id}")
                tool_ids_raw = notes.get("tool_ids", "*")
                tool_ids = tool_ids_raw.split(",") if tool_ids_raw else ["*"]
                await grant_pass(
                    user,
                    item_id,
                    tool_ids,
                    "razorpay",
                    db,
                    razorpay_payment_id=payment_id,
                    auto_commit=False,
                )
                logger.info(
                    "Pass granted via webhook: user=%s pass=%s payment=%s",
                    user.id,
                    safe_item_id,
                    safe_payment_id,
                )

            elif item_type == "credit":
                pack = get_credit_pack(item_id)
                if not pack:
                    logger.error("Unknown credit pack in webhook: %s", safe_item_id)
                    pe.status = "error"
                    await db.commit()
                    raise HTTPException(400, f"Unknown credit pack: {item_id}")
                await grant_credits(
                    user,
                    pack["credits"],
                    "purchase",
                    db,
                    razorpay_payment_id=payment_id,
                    auto_commit=False,
                )
                logger.info(
                    "Credits granted via webhook: user=%s pack=%s credits=%d payment=%s",
                    user.id,
                    safe_item_id,
                    pack["credits"],
                    safe_payment_id,
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


def _validate_payment_amount(
    item_type: str | None,
    item_id: str | None,
    amount: int | None,
    currency: str | None,
    user_id: uuid.UUID,
    order_id: str | None,
) -> None:
    """Validate that the payment amount matches catalog pricing.

    Logs a warning on mismatch but does not block fulfillment — Razorpay's
    signature verification already guarantees the payment is authentic.
    """
    if not amount or not item_type:
        return

    expected: int | None = None
    if item_type == "pro_subscription":
        for pricing in PRO_PLAN_PRICES.values():
            if pricing["currency"].upper() == (currency or "").upper():
                expected = pricing["amount"]
                break
    elif item_type in ("pass", "credit") and item_id:
        # Collect all catalog prices across regions and warn if the paid
        # amount does not match any of them.
        catalog_prices: list[int] = []
        for region in ("IN", "US", "GB", "EU"):
            price = get_price(item_id, region)
            if price is not None and price not in catalog_prices:
                catalog_prices.append(price)
        if amount in catalog_prices:
            expected = amount
        elif catalog_prices:
            logger.warning(
                "Payment amount mismatch: expected_one_of=%s got=%s item_type=%s "
                "item_id=%s user=%s order=%s",
                str(catalog_prices).replace("\n", "").replace("\r", ""),
                str(amount).replace("\n", "").replace("\r", ""),
                str(item_type).replace("\n", "").replace("\r", ""),
                str(item_id).replace("\n", "").replace("\r", ""),
                str(user_id).replace("\n", "").replace("\r", ""),
                str(order_id).replace("\n", "").replace("\r", ""),
            )

    if expected is not None and expected != amount:
        logger.warning(
            "Payment amount mismatch: expected=%s got=%s item_type=%s "
            "item_id=%s user=%s order=%s",
            str(expected).replace("\n", "").replace("\r", ""),
            str(amount).replace("\n", "").replace("\r", ""),
            str(item_type).replace("\n", "").replace("\r", ""),
            str(item_id).replace("\n", "").replace("\r", ""),
            str(user_id).replace("\n", "").replace("\r", ""),
            str(order_id).replace("\n", "").replace("\r", ""),
        )
