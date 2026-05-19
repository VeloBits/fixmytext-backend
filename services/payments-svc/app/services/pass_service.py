"""Pass service — unified tool access checking, pass/credit granting and consuming."""

import random
import secrets
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy import cast as sa_cast
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.pass_catalog import (
    ALWAYS_FREE_TOOL_IDS,
    REFERRAL_REWARDS,
    SPIN_REWARDS,
    get_pass,
)
from app.db.models.billing_credit import BillingUserCredit
from app.db.models.billing_pass import BillingUserPass, UserPassTool
from app.db.models.user import User
from app.db.models.user_daily_login import UserDailyLogin
from app.db.models.user_discovered_tool import UserDiscoveredTool
from app.db.models.user_spin_log import UserSpinLog
from app.db.models.user_tool_usage import UserToolUsage
from app.db.models.visitor_tool_usage import VisitorToolUsage
from app.db.models.visitor_usage import VisitorUsage


async def get_subscription_tier(user_id, db: AsyncSession) -> str:
    """Return 'pro' if user has an active Pro subscription, else 'free'."""
    from app.db.models.billing_subscription import Subscription

    result = await db.execute(
        select(Subscription.tier)
        .where(
            and_(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.tier == "pro",
            )
        )
        .limit(1)
    )
    return "pro" if result.scalar() else "free"


# ── New-table helper functions ────────────────────────────────────────────────


async def get_tool_use_count_today(user_id: str, tool_id: str, db: AsyncSession) -> int:
    """Return how many times *user_id* has used *tool_id* today."""
    result = await db.execute(
        select(UserToolUsage.use_count).where(
            and_(
                UserToolUsage.user_id == user_id,
                UserToolUsage.tool_id == tool_id,
                UserToolUsage.usage_date == date.today(),
            )
        )
    )
    row = result.scalar()
    return row if row is not None else 0


async def increment_tool_usage(user_id: str, tool_id: str, db: AsyncSession) -> int:
    """UPSERT a row in user_tool_usage and return the new count."""
    stmt = (
        pg_insert(UserToolUsage)
        .values(
            user_id=user_id,
            tool_id=tool_id,
            usage_date=date.today(),
            use_count=1,
        )
        .on_conflict_do_update(
            index_elements=[
                UserToolUsage.user_id,
                UserToolUsage.tool_id,
                UserToolUsage.usage_date,
            ],
            set_={"use_count": UserToolUsage.use_count + 1},
        )
    )
    await db.execute(stmt)
    return await get_tool_use_count_today(user_id, tool_id, db)


async def get_all_tool_uses_today(user_id: str, db: AsyncSession) -> dict[str, int]:
    """Return {tool_id: use_count} for all tools used by *user_id* today."""
    result = await db.execute(
        select(UserToolUsage.tool_id, UserToolUsage.use_count).where(
            and_(
                UserToolUsage.user_id == user_id,
                UserToolUsage.usage_date == date.today(),
            )
        )
    )
    return {row.tool_id: row.use_count for row in result.all()}


async def get_visitor_tool_use_count_today(
    visitor_id: str, tool_id: str, db: AsyncSession
) -> int:
    """Return how many times *visitor_id* has used *tool_id* today."""
    result = await db.execute(
        select(VisitorToolUsage.use_count).where(
            and_(
                VisitorToolUsage.visitor_id == visitor_id,
                VisitorToolUsage.tool_id == tool_id,
                VisitorToolUsage.usage_date == date.today(),
            )
        )
    )
    row = result.scalar()
    return row if row is not None else 0


async def increment_visitor_tool_usage(
    visitor_id: str, tool_id: str, db: AsyncSession
) -> int:
    """UPSERT a row in visitor_tool_usage and return the new count."""
    stmt = (
        pg_insert(VisitorToolUsage)
        .values(
            visitor_id=visitor_id,
            tool_id=tool_id,
            usage_date=date.today(),
            use_count=1,
        )
        .on_conflict_do_update(
            index_elements=[
                VisitorToolUsage.visitor_id,
                VisitorToolUsage.tool_id,
                VisitorToolUsage.usage_date,
            ],
            set_={"use_count": VisitorToolUsage.use_count + 1},
        )
    )
    await db.execute(stmt)
    return await get_visitor_tool_use_count_today(visitor_id, tool_id, db)


async def has_logged_in_today(user_id, db: AsyncSession) -> bool:
    """Check if user has a daily login record for today."""
    result = await db.execute(
        select(UserDailyLogin).where(
            and_(
                UserDailyLogin.user_id == user_id,
                UserDailyLogin.login_date == date.today(),
            )
        )
    )
    return result.scalars().first() is not None


async def record_tool_discovery(user_id: str, tool_id: str, db: AsyncSession) -> None:
    """Record that a user discovered a tool. Fire-and-forget, ignores duplicates."""
    stmt = (
        pg_insert(UserDiscoveredTool)
        .values(
            user_id=user_id,
            tool_id=tool_id,
        )
        .on_conflict_do_nothing()
    )
    await db.execute(stmt)
    await db.commit()


# ── Shared daily-limit helper ─────────────────────────────────────────────────


async def _check_daily_limit(
    entity_type: str,
    entity_id: str,
    tool_id: str,
    daily_limit: int,
    db: AsyncSession,
) -> dict | None:
    """Check if an entity (user or visitor) has remaining daily uses for a tool.

    Returns an access-allowed dict with usage counts if under the limit, or
    an access-denied dict if the limit is reached. Returns ``None`` if the
    entity type is unrecognised (should not happen in practice).

    Args:
        entity_type: Either ``"user"`` or ``"visitor"``.
        entity_id: The user ID or visitor ID.
        tool_id: The tool being accessed.
        daily_limit: Maximum free uses allowed per day.
        db: Async database session.
    """
    if entity_type == "user":
        uses = await get_tool_use_count_today(entity_id, tool_id, db)
    elif entity_type == "visitor":
        uses = await get_visitor_tool_use_count_today(entity_id, tool_id, db)
    else:
        return None

    if uses >= daily_limit:
        return {
            "allowed": False,
            "reason": "blocked",
            "uses_today": uses,
            "max_free": daily_limit,
        }

    # Increment usage
    if entity_type == "user":
        new_count = await increment_tool_usage(entity_id, tool_id, db)
    else:
        new_count = await increment_visitor_tool_usage(entity_id, tool_id, db)

    return {
        "allowed": True,
        "reason": "free",
        "uses_today": new_count,
        "max_free": daily_limit,
    }


# ── Tool access check (authenticated users) ─────────────────────────────────


async def check_tool_access(
    user: User,
    tool_id: str,
    tool_type: str,
    db: AsyncSession,
) -> dict:
    """Check if an authenticated user can use a tool.

    Checks access sources in priority order: always-free tools, Pro
    subscription, active passes, credit balance, and finally the daily
    free-use limit. Returns a dict with ``allowed`` (bool) and ``reason``.
    """
    today_str = date.today().isoformat()

    # Always-free tools
    if tool_id in ALWAYS_FREE_TOOL_IDS or tool_type == "drawer":
        return {"allowed": True, "reason": "free"}

    # Pro subscriber
    if await get_subscription_tier(user.id, db) == "pro":
        return {"allowed": True, "reason": "pro"}

    # Check active passes
    pass_result = await _check_passes(user, tool_id, today_str, db)
    if pass_result:
        return pass_result

    # Check credit balance
    credit_result = await _check_credits(user, db)
    if credit_result:
        return credit_result

    # Check daily free limit using shared helper
    max_free = settings.FREE_USES_PER_TOOL_PER_DAY
    if await has_logged_in_today(user.id, db):
        max_free += settings.DAILY_LOGIN_BONUS

    result = await _check_daily_limit("user", user.id, tool_id, max_free, db)
    if result and result["allowed"]:
        await db.commit()
        return result

    if result and not result["allowed"]:
        result["message"] = f"Daily limit reached for this tool ({max_free} uses)."
        return result

    # Fallback — should not be reached
    return {
        "allowed": False,
        "reason": "blocked",
        "message": "Access denied.",
    }


async def _check_passes(
    user: User, tool_id: str, today_str: str, db: AsyncSession
) -> dict | None:
    """Check if any active pass covers this tool with remaining uses."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(BillingUserPass)
        .options(selectinload(BillingUserPass.tools))
        .where(
            and_(
                BillingUserPass.user_id == user.id,
                BillingUserPass.is_active == True,  # noqa: E712
                BillingUserPass.expires_at > now,
            )
        )
    )
    passes = result.scalars().all()

    for p in passes:
        # Reset pass daily uses if needed (date comparison, not string)
        if p.uses_reset_date != date.today():
            p.uses_today = 0
            p.uses_reset_date = date.today()

        # Check if this pass covers the tool
        covers = p.tools_count == -1 or any(
            t.tool_id in ("*", tool_id) for t in p.tools
        )
        if covers and p.uses_today < p.uses_per_day:
            p.uses_today += 1
            await db.commit()
            return {
                "allowed": True,
                "reason": "pass",
                "pass_name": (
                    get_pass(p.pass_id)["name"] if get_pass(p.pass_id) else p.pass_id
                ),
            }

    return None


async def _check_credits(user: User, db: AsyncSession) -> dict | None:
    """Check if user has any remaining credits. Consume one if so (FIFO order)."""
    result = await db.execute(
        select(BillingUserCredit)
        .where(
            and_(
                BillingUserCredit.user_id == user.id,
                BillingUserCredit.credits_remaining > 0,
            )
        )
        .order_by(BillingUserCredit.created_at.asc())  # FIFO
    )
    credit = result.scalars().first()
    if credit:
        credit.credits_remaining -= 1
        await db.commit()
        total_remaining = await get_credit_balance(user, db)
        return {
            "allowed": True,
            "reason": "credit",
            "credits_remaining": total_remaining,
        }
    return None


# ── Visitor access check (unauthenticated) ───────────────────────────────────


async def check_visitor_access(
    fingerprint: str,
    ip_address: str,
    tool_id: str,
    tool_type: str,
    db: AsyncSession,
) -> dict:
    """Check tool access for an unauthenticated visitor using fingerprint + IP.

    Creates a new visitor record if none exists. Uses the shared daily-limit
    helper for usage tracking.
    """
    if tool_id in ALWAYS_FREE_TOOL_IDS or tool_type == "drawer":
        return {"allowed": True, "reason": "free"}

    # Find by fingerprint or IP in a single locked query to prevent race conditions
    visitor = None
    conditions = []
    if fingerprint:
        conditions.append(VisitorUsage.fingerprint == fingerprint)
    if ip_address:
        conditions.append(VisitorUsage.ip_address == sa_cast(ip_address, INET))

    if conditions:
        result = await db.execute(
            select(VisitorUsage).where(or_(*conditions)).with_for_update().limit(1)
        )
        visitor = result.scalars().first()

    if visitor:
        # Check daily limit using shared helper
        limit_result = await _check_daily_limit(
            "visitor",
            visitor.id,
            tool_id,
            settings.FREE_USES_PER_TOOL_PER_DAY,
            db,
        )
        if limit_result and not limit_result["allowed"]:
            limit_result["message"] = "Sign in to get more free uses, or buy a pass!"
            return limit_result

        # Update fingerprint/IP if we found by the other
        if fingerprint and visitor.fingerprint != fingerprint:
            visitor.fingerprint = fingerprint
        if ip_address and str(visitor.ip_address) != ip_address:
            visitor.ip_address = ip_address
        await db.commit()
        return limit_result if limit_result else {"allowed": True, "reason": "free"}

    # New visitor
    new_visitor = VisitorUsage(
        fingerprint=fingerprint or "unknown",
        ip_address=ip_address or None,
    )
    db.add(new_visitor)
    await db.flush()  # get new_visitor.id for the new-table insert

    # Also insert into new table
    await increment_visitor_tool_usage(new_visitor.id, tool_id, db)

    await db.commit()
    return {"allowed": True, "reason": "free", "uses_today": 1}


# ── Grant pass ───────────────────────────────────────────────────────────────


async def grant_pass(
    user: User,
    pass_id: str,
    tool_ids: list[str],
    source: str,
    db: AsyncSession,
    razorpay_payment_id: str | None = None,
    auto_commit: bool = True,
) -> BillingUserPass:
    """Create a BillingUserPass + UserPassTool rows for the given user.

    Args:
        user: The user receiving the pass.
        pass_id: Catalog pass identifier (e.g. ``"day_triple"``).
        tool_ids: List of tool IDs covered, or ``["*"]`` for all tools.
        source: How the pass was acquired (``"razorpay"``, ``"spin"``, etc.).
        db: Async database session.
        razorpay_payment_id: Optional Razorpay payment ID for audit.
        auto_commit: Whether to commit the transaction automatically.

    Returns:
        The newly created ``BillingUserPass`` instance.

    Raises:
        ValueError: If ``pass_id`` is not found in the catalog.
    """
    pass_def = get_pass(pass_id)
    if not pass_def:
        raise ValueError(f"Unknown pass: {pass_id}")

    now = datetime.now(UTC)
    expires = now + timedelta(days=pass_def["duration_days"])

    # For "all tools" passes, store ["*"]
    if pass_def["tools"] == -1:
        tool_ids = ["*"]

    billing_pass = BillingUserPass(
        user_id=user.id,
        pass_id=pass_id,
        tools_count=pass_def["tools"],
        uses_per_day=pass_def["uses_per_day"],
        source=source,
        expires_at=expires,
        razorpay_payment_id=razorpay_payment_id,
    )
    db.add(billing_pass)
    await db.flush()  # get billing_pass.id for junction rows

    for tid in tool_ids:
        db.add(UserPassTool(pass_instance_id=billing_pass.id, tool_id=tid))

    if auto_commit:
        await db.commit()
    return billing_pass


# ── Grant credits ────────────────────────────────────────────────────────────


async def grant_credits(
    user: User,
    amount: int,
    source: str,
    db: AsyncSession,
    razorpay_payment_id: str | None = None,
    auto_commit: bool = True,
) -> BillingUserCredit:
    """Add credits to the user's balance.

    Creates a new ``BillingUserCredit`` row; credits are consumed FIFO by
    ``_check_credits()``.
    """
    billing_credit = BillingUserCredit(
        user_id=user.id,
        credits_total=amount,
        credits_remaining=amount,
        source=source,
        razorpay_payment_id=razorpay_payment_id,
    )
    db.add(billing_credit)

    if auto_commit:
        await db.commit()
    return billing_credit


# ── Credit balance ───────────────────────────────────────────────────────────


async def get_credit_balance(user: User, db: AsyncSession) -> int:
    """Return total remaining credits across all credit packs for this user."""
    result = await db.execute(
        select(func.coalesce(func.sum(BillingUserCredit.credits_remaining), 0)).where(
            and_(
                BillingUserCredit.user_id == user.id,
                BillingUserCredit.credits_remaining > 0,
            )
        )
    )
    return result.scalar()


# ── Active passes ────────────────────────────────────────────────────────────


async def get_active_passes(user: User, db: AsyncSession) -> list[BillingUserPass]:
    """Return all non-expired active passes for this user, earliest-expiring first."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(BillingUserPass)
        .options(selectinload(BillingUserPass.tools))
        .where(
            and_(
                BillingUserPass.user_id == user.id,
                BillingUserPass.is_active == True,  # noqa: E712
                BillingUserPass.expires_at > now,
            )
        )
        .order_by(BillingUserPass.expires_at.asc())
    )
    return result.scalars().all()


# ── Active credits ───────────────────────────────────────────────────────────


async def get_active_credits(user: User, db: AsyncSession) -> list[BillingUserCredit]:
    """Return all credit rows with remaining balance (oldest first)."""
    result = await db.execute(
        select(BillingUserCredit)
        .where(
            and_(
                BillingUserCredit.user_id == user.id,
                BillingUserCredit.credits_remaining > 0,
            )
        )
        .order_by(BillingUserCredit.created_at.asc())
    )
    return result.scalars().all()


# ── Daily login bonus ────────────────────────────────────────────────────────


async def record_daily_login(user: User, db: AsyncSession) -> bool:
    """Record daily login. Returns True if this is the first login today (bonus granted)."""
    today = date.today()

    stmt = (
        pg_insert(UserDailyLogin)
        .values(
            user_id=user.id,
            login_date=today,
        )
        .on_conflict_do_nothing()
    )
    result = await db.execute(stmt)

    await db.commit()
    # rowcount == 1 means this was the first login today
    return result.rowcount == 1


# ── Spin the wheel ───────────────────────────────────────────────────────────


async def spin_wheel(user: User, db: AsyncSession) -> dict:
    """Spin the weekly reward wheel.

    Each user gets one spin per ISO week. Returns a dict describing the
    reward (credits or a pass), or an ``{"error": ...}`` dict if already spun.
    """
    today = date.today()
    iso_cal = today.isocalendar()

    # Check if already spun this week
    result = await db.execute(
        select(UserSpinLog).where(
            and_(
                UserSpinLog.user_id == user.id,
                UserSpinLog.iso_year == iso_cal[0],
                UserSpinLog.iso_week == iso_cal[1],
            )
        )
    )
    existing_spin = result.scalars().first()
    if existing_spin:
        return {"error": "Already spun this week. Come back next week!"}

    # Weighted random selection
    total_weight = sum(r["weight"] for r in SPIN_REWARDS)
    roll = random.randint(1, total_weight)  # noqa: S311
    cumulative = 0
    reward = SPIN_REWARDS[-1]
    for r in SPIN_REWARDS:
        cumulative += r["weight"]
        if roll <= cumulative:
            reward = r
            break

    # Determine reward_ref for the spin log
    if reward["type"] == "credits":
        reward_ref = str(reward["amount"])
    else:
        reward_ref = reward["pass_id"]

    # Insert into spin log table
    spin_log = UserSpinLog(
        user_id=user.id,
        iso_year=iso_cal[0],
        iso_week=iso_cal[1],
        spin_date=today,
        reward_type=reward["type"],
        reward_ref=reward_ref,
    )
    db.add(spin_log)

    # Flush the spin log insert first — if it violates the weekly uniqueness
    # constraint, surface the friendly "already spun" message without masking
    # unrelated integrity errors from grant_pass/grant_credits.
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return {"error": "Already spun this week. Come back next week!"}

    if reward["type"] == "credits":
        await grant_credits(user, reward["amount"], "spin", db, auto_commit=False)
        await db.commit()
        return {
            "reward_type": "credits",
            "amount": reward["amount"],
            "message": f"You won {reward['amount']} credits!",
        }
    else:
        pass_def = get_pass(reward["pass_id"])
        if not pass_def:
            raise ValueError(f"Invalid spin reward pass_id: {reward['pass_id']}")
        await grant_pass(user, reward["pass_id"], ["*"], "spin", db, auto_commit=False)
        await db.commit()
        return {
            "reward_type": "pass",
            "pass_id": reward["pass_id"],
            "pass_name": pass_def["name"],
            "message": f"You won a {pass_def['name']} pass!",
        }


# ── Referral code ────────────────────────────────────────────────────────────


async def ensure_referral_code(user: User, db: AsyncSession) -> str:
    """Generate a referral code for the user if they don't already have one."""
    if user.referral_code:
        return user.referral_code
    code = secrets.token_urlsafe(8)[:10].upper()
    user.referral_code = code
    await db.commit()
    return code


async def claim_referral(user: User, code: str, db: AsyncSession) -> dict:
    """Claim a referral code, granting rewards to both parties atomically.

    The user row is locked to prevent concurrent referral claims. Rewards
    are granted within a single transaction that rolls back on failure.
    """
    # Lock user row to prevent concurrent referral claims
    locked = await db.execute(select(User).where(User.id == user.id).with_for_update())
    user = locked.scalars().first()

    if user.referred_by:
        return {"error": "You've already used a referral code."}
    if user.referral_code == code:
        return {"error": "You can't use your own referral code."}

    result = await db.execute(select(User).where(User.referral_code == code))
    referrer = result.scalars().first()
    if not referrer:
        return {"error": "Invalid referral code."}

    try:
        # Reward referrer
        rr = REFERRAL_REWARDS["referrer"]
        await grant_pass(
            referrer, rr["pass_id"], ["*"], "referral", db, auto_commit=False
        )
        await grant_credits(referrer, rr["credits"], "referral", db, auto_commit=False)

        # Reward new user
        nr = REFERRAL_REWARDS["new_user"]
        await grant_credits(user, nr["credits"], "referral", db, auto_commit=False)

        # Mark as referred only after all rewards are staged
        user.referred_by = referrer.id
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {"success": True, "message": "Referral claimed! You got 10 credits."}
