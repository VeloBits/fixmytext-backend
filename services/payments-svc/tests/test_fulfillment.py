"""Idempotency / exactly-once tests for the payment fulfillment authority.

Proves C-1 (payment replay), H-2 (verify/webhook double-grant) and H-11 (Pro
double-verify → 500) are fixed: both client callbacks and the webhook converge
on a single ``payment_fulfillments`` ledger keyed by ``razorpay_payment_id``, so
a replay or a race grants the entitlement exactly once.

DB-backed - requires a throwaway Postgres. Set ``TEST_DATABASE_URL`` e.g.::

    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/postgres

The Pro path is exercised because it needs only the ``users``, ``subscriptions``
and ``payment_fulfillments`` tables (no catalog seeding), while sharing the exact
ledger guard used by the pass/credit paths (also asserted directly).
"""

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import PaymentFulfillment, Subscription, User
from app.db.session import Base
from app.services.fulfillment_service import AlreadyFulfilled, fulfill_payment

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="set TEST_DATABASE_URL to a throwaway Postgres to run idempotency tests",
)

_TABLES = [User.__table__, Subscription.__table__, PaymentFulfillment.__table__]


@pytest.fixture
async def session_factory():
    """Create the minimal schema on a throwaway Postgres and yield a sessionmaker."""
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS billing"))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS billing CASCADE"))
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        await engine.dispose()


@pytest.fixture
async def user(session_factory):
    async with session_factory() as db:
        u = User(
            email=f"u-{uuid.uuid4().hex[:8]}@test.test",
            display_name="Test User",
            region="IN",
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


async def _fulfill_pro(factory, user, payment_id, order_id="order_x", via="verify"):
    """Mirror an endpoint: lock the user row, fulfill Pro, commit/rollback.

    Returns "fulfilled" on a fresh grant or "already" when the payment was
    already fulfilled (replay or pre-existing active subscription).
    """
    async with factory() as db:
        await db.execute(select(User).where(User.id == user.id).with_for_update())
        try:
            await fulfill_payment(
                db=db,
                user=user,
                razorpay_payment_id=payment_id,
                razorpay_order_id=order_id,
                item_type="pro_subscription",
                item_id=None,
                tool_ids=[],
                amount_subunits=39900,
                currency="INR",
                fulfilled_via=via,
            )
            await db.commit()
            return "fulfilled"
        except AlreadyFulfilled:
            await db.rollback()
            return "already"


# ── C-1 / H-2: replaying the same payment grants exactly once ────────────────


async def test_replay_same_payment_id_grants_once(session_factory, user):
    first = await _fulfill_pro(session_factory, user, "pay_replay")
    second = await _fulfill_pro(session_factory, user, "pay_replay", via="webhook")

    assert first == "fulfilled"
    assert second == "already"

    async with session_factory() as db:
        subs = (
            (
                await db.execute(
                    select(Subscription).where(Subscription.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        ledger = (
            (
                await db.execute(
                    select(PaymentFulfillment).where(
                        PaymentFulfillment.razorpay_payment_id == "pay_replay"
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(subs) == 1, "replay must not create a second subscription"
    assert len(ledger) == 1, "exactly one ledger row per payment id"
    assert ledger[0].status == "fulfilled"
    assert ledger[0].fulfilled_via == "verify"  # the first writer won


# ── H-11 / REL-01: a second distinct payment is idempotent, never a 500 ──────


async def test_second_distinct_payment_same_user_is_idempotent(session_factory, user):
    first = await _fulfill_pro(session_factory, user, "pay_A")
    second = await _fulfill_pro(session_factory, user, "pay_B")

    assert first == "fulfilled"
    # The one-active-subscription index makes the second resolve as already
    # fulfilled instead of raising IntegrityError -> 500.
    assert second == "already"

    async with session_factory() as db:
        active = (
            (
                await db.execute(
                    select(Subscription).where(
                        Subscription.user_id == user.id,
                        Subscription.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        ledger = (await db.execute(select(PaymentFulfillment))).scalars().all()

    assert len(active) == 1
    # pay_B rolled back, so only pay_A's ledger row persists.
    assert {row.razorpay_payment_id for row in ledger} == {"pay_A"}


# ── The DB guard that underpins pass & credit idempotency too ────────────────


async def test_ledger_unique_index_blocks_duplicate_payment_id(session_factory, user):
    async with session_factory() as db:
        db.add(
            PaymentFulfillment(
                razorpay_payment_id="dup",
                user_id=user.id,
                item_type="pass",
                fulfilled_via="verify",
                status="fulfilled",
            )
        )
        await db.commit()

    async with session_factory() as db:
        db.add(
            PaymentFulfillment(
                razorpay_payment_id="dup",
                user_id=user.id,
                item_type="pass",
                fulfilled_via="webhook",
                status="fulfilled",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
