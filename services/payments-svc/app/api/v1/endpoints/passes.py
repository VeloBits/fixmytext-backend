"""Pass & credit endpoints: catalog, active, order, verify, spin, referral."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.pass_catalog import (
    CREDIT_PACKS,
    PASSES,
    REGIONS,
    get_credit_pack,
    get_currency,
    get_pass,
    get_price,
    get_symbol,
)
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.passes import (
    ActiveCredit,
    ActivePass,
    ActiveResponse,
    CatalogResponse,
    ClaimReferralRequest,
    CreditOrderRequest,
    CreditPackItem,
    PassCatalogItem,
    PassOrderRequest,
    RazorpayOrderResponse,
    RazorpayVerifyRequest,
    ReferralCodeResponse,
    SpinResult,
)
from app.services.fulfillment_service import AlreadyFulfilled, fulfill_payment
from app.services.order_validation import validate_order_scope_and_amount
from app.services.pass_service import (
    claim_referral,
    ensure_referral_code,
    get_active_credits,
    get_active_passes,
    get_credit_balance,
    maybe_grant_welcome_gift,
    spin_wheel,
)
from app.services.payment_service import verify_razorpay_payment
from app.services.rate_limit import check_rate_limit
from app.services.razorpay_service import create_order, payments_configured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/passes", tags=["Passes"])


# ── Catalog ─────────────────────────────────────────────────────────────


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(request: Request, region: str = ""):
    """Return all available passes and credit packs with regional pricing.

    Auto-detects region from the client's IP address if not provided or invalid.
    """
    if not region or region not in REGIONS:
        from app.services.region_service import detect_region

        ip = request.client.host if request.client else ""
        region = await detect_region(ip)
        # detect_region() always returns a REGIONS-valid code or its own
        # DEFAULT_REGION ("US"), so no second fallback guard is needed here.

    currency = get_currency(region)
    symbol = get_symbol(region)

    passes = [
        PassCatalogItem(
            id=p["id"],
            name=p["name"],
            subtitle=p["subtitle"],
            tools=p["tools"],
            uses_per_day=p["uses_per_day"],
            duration_days=p["duration_days"],
            price=get_price(p["id"], region),
            currency=currency,
            symbol=symbol,
        )
        for p in PASSES
    ]

    credit_packs = [
        CreditPackItem(
            id=c["id"],
            name=c["name"],
            credits=c["credits"],
            price=get_price(c["id"], region),
            currency=currency,
            symbol=symbol,
        )
        for c in CREDIT_PACKS
    ]

    return CatalogResponse(passes=passes, credit_packs=credit_packs, region=region)


# ── Active Passes & Credits ────────────────────────────────────────────────


@router.get("/active", response_model=ActiveResponse)
async def get_active(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's active passes and total credit balance."""
    passes = await get_active_passes(user, db)
    credits = await get_active_credits(user, db)
    total = await get_credit_balance(user, db)

    return ActiveResponse(
        passes=[
            ActivePass(
                id=str(p.id),
                pass_id=p.pass_id,
                name=(get_pass(p.pass_id) or {}).get("name", p.pass_id),
                tool_ids=(
                    [t.tool_id for t in p.tools]
                    if hasattr(p, "tools")
                    else (p.tool_ids or [])
                ),
                tools_count=p.tools_count,
                uses_per_day=p.uses_per_day,
                uses_today=p.uses_today,
                expires_at=p.expires_at,
                source=p.source,
            )
            for p in passes
        ],
        credits=[
            ActiveCredit(
                id=str(c.id),
                credits_remaining=c.credits_remaining,
                credits_total=c.credits_total,
                source=c.source,
            )
            for c in credits
        ],
        total_credits=total,
    )


# ── Razorpay: Create Order (pass) ──────────────────────────────────────────


@router.post("/order", response_model=RazorpayOrderResponse)
async def create_pass_order(
    req: PassOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Razorpay order for purchasing a pass.

    Resolves the user's region (from explicit param, stored value, or IP),
    then creates a Razorpay order with the correct regional pricing.
    """
    if not payments_configured():
        raise HTTPException(503, "Payments not configured")
    await check_rate_limit(
        f"ratelimit:order:{user.id}", settings.ORDER_RATE_LIMIT_PER_MINUTE
    )

    pass_def = get_pass(req.pass_id)
    if not pass_def:
        raise HTTPException(400, f"Unknown pass: {req.pass_id}")

    from app.services.region_service import resolve_user_region

    region = await resolve_user_region(user, None, db, explicit_region=req.region)
    await db.flush()  # Ensure region changes are flushed within the session
    amount = get_price(req.pass_id, region)
    currency = get_currency(region)

    idempotency_key = f"pass_{req.pass_id}_{user.id}"
    try:
        order = create_order(
            amount=amount,
            currency=currency,
            receipt=f"pass_{req.pass_id}_{str(user.id)[:8]}",
            notes={
                "user_id": str(user.id),
                "item_id": req.pass_id,
                "item_type": "pass",
                "tool_ids": ",".join(req.tool_ids),
            },
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception("Failed to create Razorpay order for pass %s, user %s", req.pass_id, user.id)
        raise HTTPException(502, "Failed to start checkout — please try again later")
    return RazorpayOrderResponse(
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
        key_id=settings.RAZORPAY_KEY_ID,
        user_email=user.email,
        user_name=user.display_name,
    )


# ── Razorpay: Create Order (credits) ───────────────────────────────────────


@router.post("/credit-order", response_model=RazorpayOrderResponse)
async def create_credit_order(
    req: CreditOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Razorpay order for purchasing a credit pack.

    Resolves the user's region and returns a Razorpay order with pricing
    in the correct currency.
    """
    if not payments_configured():
        raise HTTPException(503, "Payments not configured")
    await check_rate_limit(
        f"ratelimit:order:{user.id}", settings.ORDER_RATE_LIMIT_PER_MINUTE
    )

    pack = get_credit_pack(req.pack_id)
    if not pack:
        raise HTTPException(400, f"Unknown credit pack: {req.pack_id}")

    from app.services.region_service import resolve_user_region

    region = await resolve_user_region(user, None, db, explicit_region=req.region)
    await db.flush()  # Ensure region changes are flushed within the session
    amount = get_price(req.pack_id, region)
    currency = get_currency(region)

    idempotency_key = f"credit_{req.pack_id}_{user.id}"
    try:
        order = create_order(
            amount=amount,
            currency=currency,
            receipt=f"credit_{req.pack_id}_{str(user.id)[:8]}",
            notes={"user_id": str(user.id), "item_id": req.pack_id, "item_type": "credit"},
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception("Failed to create Razorpay order for credit pack %s, user %s", req.pack_id, user.id)
        raise HTTPException(502, "Failed to start checkout — please try again later")
    return RazorpayOrderResponse(
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
        key_id=settings.RAZORPAY_KEY_ID,
        user_email=user.email,
        user_name=user.display_name,
    )


# ── Razorpay: Verify Payment ───────────────────────────────────────────────


@router.post("/verify")
async def verify_pass_payment(
    req: RazorpayVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a Razorpay payment signature, then grant the purchased pass or credits.

    Fulfillment is idempotent and exactly-once: this verify callback and the
    Razorpay webhook converge on a single ledger keyed by the payment id, so a
    replayed body or a verify/webhook race grants the entitlement only once.
    Tool scope and the paid amount are validated server-side against the order
    notes and the catalog — the client-supplied ``tool_ids`` are ignored.
    """
    # Verify signature and ownership via centralized payment service
    order = await verify_razorpay_payment(
        req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature, user
    )

    # Server-side scope + amount validation. tool_ids come from the order notes
    # fixed at creation time, NOT from req.tool_ids; amount is reconciled against
    # the catalog price for the charged currency.
    tool_ids, amount, currency = validate_order_scope_and_amount(
        order=order, expected_item_id=req.item_id, expected_item_type=req.item_type
    )

    # Lock the user row so the welcome-gift check is atomic against the webhook.
    await db.execute(select(User).where(User.id == user.id).with_for_update())

    safe_item_id = str(req.item_id).replace("\r", "").replace("\n", "")
    safe_payment_id = str(req.razorpay_payment_id).replace("\r", "").replace("\n", "")

    try:
        await fulfill_payment(
            db=db,
            user=user,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_order_id=req.razorpay_order_id,
            item_type=req.item_type,
            item_id=req.item_id,
            tool_ids=tool_ids,
            amount_subunits=amount,
            currency=currency,
            fulfilled_via="verify",
        )
        # First-purchase welcome gift (idempotent; user row locked above).
        if await maybe_grant_welcome_gift(user, db):
            logger.info("Welcome gift granted: user=%s", user.id)
        await db.commit()
    except AlreadyFulfilled:
        await db.rollback()
        logger.info(
            "Payment already fulfilled (verify): user=%s item=%s payment=%s",
            user.id,
            safe_item_id,
            safe_payment_id,
        )
        return {"status": "success", "detail": "already_fulfilled"}
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "Payment fulfilled (verify): user=%s type=%s item=%s payment=%s",
        user.id,
        req.item_type,
        safe_item_id,
        safe_payment_id,
    )
    return {"status": "success"}


# ── Spin the Wheel ─────────────────────────────────────────────────────────


@router.post("/spin", response_model=SpinResult)
async def do_spin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Spin the weekly reward wheel for a random prize (pass or credits)."""
    result = await spin_wheel(user, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return SpinResult(**result)


# ── Referral ───────────────────────────────────────────────────────────────


@router.get("/referral-code", response_model=ReferralCodeResponse)
async def get_referral_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or generate the authenticated user's unique referral code and URL."""
    code = await ensure_referral_code(user, db)
    return ReferralCodeResponse(
        referral_code=code,
        referral_url=f"{settings.FRONTEND_URL}/signup?ref={code}",
    )


@router.post("/claim-referral")
async def do_claim_referral(
    req: ClaimReferralRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Claim a referral code, granting rewards to both the referrer and the new user."""
    result = await claim_referral(user, req.code, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result
