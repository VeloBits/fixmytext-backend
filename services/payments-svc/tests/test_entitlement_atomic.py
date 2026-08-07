"""Atomic check-and-consume tests for the restored entitlement gate.

Proves BE-DATA-01 (pass uses), BE-DATA-02 (credit balance) and BE-PAY-06: under
concurrent requests the per-tool consumption never exceeds the cap and the credit
balance never goes negative - the read-modify-write races are gone.

DB-backed - requires a throwaway Postgres. Set ``TEST_DATABASE_URL``.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import (
    BillingUserCredit,
    BillingUserPass,
    PassCatalog,
    User,
)
from app.db.session import Base
from app.services.pass_service import (
    check_tool_access,
    check_visitor_access,
    claim_referral,
)

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="set TEST_DATABASE_URL to a throwaway Postgres to run atomicity tests",
)


@pytest.fixture
async def factory():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS billing"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS activity"))
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield sm
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS activity CASCADE"))
            await conn.execute(text("DROP SCHEMA IF EXISTS billing CASCADE"))
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
        await engine.dispose()


@pytest.fixture
async def user_id(factory):
    async with factory() as db:
        u = User(
            email=f"u-{uuid.uuid4().hex[:8]}@test.test",
            display_name="T",
            region="IN",
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u.id


async def _check_user(factory, uid, tool="uppercase", ttype="local"):
    async with factory() as db:
        user = await db.get(User, uid)
        return await check_tool_access(user, tool, ttype, db)


# ── BE-DATA-02: credit decrement is atomic ───────────────────────────────────


async def test_concurrent_credit_consume_never_negative(factory, user_id):
    async with factory() as db:
        db.add(
            BillingUserCredit(
                user_id=user_id,
                credits_total=1,
                credits_remaining=1,
                source="test",
            )
        )
        await db.commit()

    results = await asyncio.gather(*[_check_user(factory, user_id) for _ in range(10)])

    credit_grants = [r for r in results if r["reason"] == "credit"]
    assert len(credit_grants) == 1, "exactly one request may spend the single credit"

    async with factory() as db:
        remaining = (
            await db.execute(
                select(BillingUserCredit.credits_remaining).where(
                    BillingUserCredit.user_id == user_id
                )
            )
        ).scalar()
    assert remaining == 0, "balance must land at 0, never negative"


# ── BE-DATA-01 / BE-PAY-06: pass uses never exceed the daily cap ─────────────


async def test_concurrent_pass_uses_never_exceed_cap(factory, user_id):
    async with factory() as db:
        db.add(
            PassCatalog(
                id="day_all",
                name="Day All",
                subtitle="all tools",
                tools_count=-1,
                uses_per_day=3,
                duration_days=1,
            )
        )
        db.add(
            BillingUserPass(
                user_id=user_id,
                pass_id="day_all",
                tools_count=-1,  # covers every tool
                uses_per_day=3,
                source="test",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                uses_today=0,
                uses_reset_date=None,
            )
        )
        await db.commit()

    results = await asyncio.gather(*[_check_user(factory, user_id) for _ in range(10)])

    pass_grants = [r for r in results if r["reason"] == "pass"]
    assert len(pass_grants) == 3, "pass may be consumed at most uses_per_day times"

    async with factory() as db:
        uses_today = (
            await db.execute(
                select(BillingUserPass.uses_today).where(
                    BillingUserPass.user_id == user_id
                )
            )
        ).scalar()
    assert uses_today == 3, "uses_today must never exceed the cap"


# ── Visitor quota with a server-derived key ──────────────────────────────────


# ── M-10: referral anti-farming ──────────────────────────────────────────────


async def test_referral_requires_verified_email(factory):
    """An unverified account can't claim a referral (blocks burner farming)."""
    async with factory() as db:
        u = User(
            email=f"u-{uuid.uuid4().hex[:8]}@test.test",
            display_name="Unverified",
            is_email_verified=False,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        result = await claim_referral(u, "SOME-FRIEND-CODE", db)
    assert "error" in result
    assert "verify" in result["error"].lower()


async def test_visitor_quota_blocks_after_free_limit(factory):
    # Default free limit is 3/tool/day. The 4th call for the same server key
    # (same IP+UA hash) must be blocked.
    key = "server-derived-fingerprint"
    ip = "203.0.113.7"
    outcomes = []
    for _ in range(4):
        async with factory() as db:
            outcomes.append(
                await check_visitor_access(key, ip, "uppercase", "local", db)
            )
    allowed = [o for o in outcomes if o["allowed"]]
    assert len(allowed) == 3
    assert outcomes[-1]["allowed"] is False
