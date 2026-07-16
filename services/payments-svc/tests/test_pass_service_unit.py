"""Unit tests for app.services.pass_service against a mocked AsyncSession.

Covers the usage counters, the check-and-consume access chain
(check_tool_access / _check_passes / _check_credits / _check_daily_limit),
visitor access, grants, the welcome gift, daily login, spin-the-wheel, and
the referral flow. The DB-backed atomicity variants live in
test_entitlement_atomic.py (require TEST_DATABASE_URL); these tests pin the
branch logic without a live Postgres.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.billing_credit import BillingUserCredit
from app.db.models.billing_pass import BillingUserPass, UserPassTool
from app.db.models.visitor_usage import VisitorUsage
from app.services.pass_service import (
    _check_credits,
    _check_daily_limit,
    _check_passes,
    check_tool_access,
    check_visitor_access,
    claim_referral,
    ensure_referral_code,
    get_active_credits,
    get_active_passes,
    get_all_tool_uses_today,
    get_credit_balance,
    get_subscription_tier,
    get_tool_use_count_today,
    get_visitor_tool_use_count_today,
    has_logged_in_today,
    increment_tool_usage,
    increment_visitor_tool_usage,
    maybe_grant_welcome_gift,
    record_daily_login,
    record_tool_discovery,
    spin_wheel,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _user(**overrides) -> SimpleNamespace:
    defaults = {
        "id": uuid.uuid4(),
        "keycloak_id": uuid.uuid4(),
        "region": "IN",
        "referral_code": None,
        "referred_by": None,
        "is_email_verified": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _result(
    *,
    first=None,
    scalar=None,
    all_rows=None,
    scalar_one_or_none=None,
    rowcount=0,
):
    res = MagicMock()
    res.scalars.return_value.first.return_value = first
    res.scalars.return_value.all.return_value = all_rows if all_rows else []
    res.scalar.return_value = scalar
    res.scalar_one_or_none.return_value = scalar_one_or_none
    res.all.return_value = all_rows if all_rows else []
    res.rowcount = rowcount
    return res


def _db(results=None, scalar=None) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    if results is None:
        db.execute = AsyncMock(return_value=_result())
    else:
        db.execute = AsyncMock(side_effect=list(results))
    db.scalar = AsyncMock(return_value=scalar)
    return db


# ── Subscription tier ─────────────────────────────────────────────────────────


async def test_get_subscription_tier_pro():
    # Any in-period subscription row (the query already filters on
    # status IN ('active','cancelled') AND expires_at > now()) means pro.
    sub = SimpleNamespace(status="active", tier="pro")
    db = _db([_result(scalar_one_or_none=sub)])
    assert await get_subscription_tier(uuid.uuid4(), db) == "pro"


async def test_get_subscription_tier_free_when_no_active_sub():
    db = _db([_result(scalar_one_or_none=None)])
    assert await get_subscription_tier(uuid.uuid4(), db) == "free"


# ── Usage counters ────────────────────────────────────────────────────────────


async def test_get_tool_use_count_today_defaults_to_zero():
    db = _db([_result(scalar=None)])
    assert await get_tool_use_count_today("u1", "uppercase", db) == 0


async def test_get_tool_use_count_today_returns_count():
    db = _db([_result(scalar=4)])
    assert await get_tool_use_count_today("u1", "uppercase", db) == 4


async def test_increment_tool_usage_upserts_and_returns_new_count():
    db = _db([_result(), _result(scalar=2)])
    assert await increment_tool_usage("u1", "uppercase", db) == 2
    assert db.execute.await_count == 2


async def test_get_all_tool_uses_today_maps_rows():
    rows = [
        SimpleNamespace(tool_id="uppercase", use_count=2),
        SimpleNamespace(tool_id="word_count", use_count=1),
    ]
    db = _db([_result(all_rows=rows)])
    assert await get_all_tool_uses_today("u1", db) == {
        "uppercase": 2,
        "word_count": 1,
    }


async def test_get_visitor_tool_use_count_today_defaults_to_zero():
    db = _db([_result(scalar=None)])
    assert await get_visitor_tool_use_count_today("v1", "uppercase", db) == 0


async def test_increment_visitor_tool_usage_upserts_and_returns_new_count():
    db = _db([_result(), _result(scalar=1)])
    assert await increment_visitor_tool_usage("v1", "uppercase", db) == 1


async def test_has_logged_in_today_true_and_false():
    assert await has_logged_in_today("u1", _db([_result(first=object())])) is True
    assert await has_logged_in_today("u1", _db([_result(first=None)])) is False


async def test_record_tool_discovery_commits():
    db = _db()
    await record_tool_discovery("u1", "uppercase", db)
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()


# ── _check_daily_limit ────────────────────────────────────────────────────────


async def test_check_daily_limit_unknown_entity_returns_none():
    assert await _check_daily_limit("robot", "x", "uppercase", 3, _db()) is None


async def test_check_daily_limit_blocks_at_cap():
    with patch(
        "app.services.pass_service.get_tool_use_count_today",
        new_callable=AsyncMock,
        return_value=3,
    ):
        result = await _check_daily_limit("user", "u1", "uppercase", 3, _db())
    assert result == {
        "allowed": False,
        "reason": "blocked",
        "uses_today": 3,
        "max_free": 3,
    }


async def test_check_daily_limit_allows_and_increments_user():
    with (
        patch(
            "app.services.pass_service.get_tool_use_count_today",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "app.services.pass_service.increment_tool_usage",
            new_callable=AsyncMock,
            return_value=1,
        ) as mock_inc,
    ):
        result = await _check_daily_limit("user", "u1", "uppercase", 3, _db())
    assert result["allowed"] is True
    assert result["reason"] == "free"
    assert result["uses_today"] == 1
    mock_inc.assert_awaited_once()


async def test_check_daily_limit_allows_and_increments_visitor():
    with (
        patch(
            "app.services.pass_service.get_visitor_tool_use_count_today",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch(
            "app.services.pass_service.increment_visitor_tool_usage",
            new_callable=AsyncMock,
            return_value=2,
        ),
    ):
        result = await _check_daily_limit("visitor", "v1", "uppercase", 3, _db())
    assert result["allowed"] is True
    assert result["uses_today"] == 2


# ── check_tool_access priority chain ──────────────────────────────────────────


async def test_check_tool_access_always_free_tool_short_circuits():
    db = _db()
    result = await check_tool_access(_user(), "password", "local", db)
    assert result == {"allowed": True, "reason": "free"}
    db.execute.assert_not_awaited()


async def test_check_tool_access_drawer_tools_are_free():
    result = await check_tool_access(_user(), "anything", "drawer", _db())
    assert result == {"allowed": True, "reason": "free"}


async def test_check_tool_access_pro_subscriber_bypasses_consumption():
    with patch(
        "app.services.pass_service.get_subscription_tier",
        new_callable=AsyncMock,
        return_value="pro",
    ):
        result = await check_tool_access(_user(), "uppercase", "local", _db())
    assert result == {"allowed": True, "reason": "pro"}


async def test_check_tool_access_consumes_pass_and_commits():
    db = _db()
    with (
        patch(
            "app.services.pass_service.get_subscription_tier",
            new_callable=AsyncMock,
            return_value="free",
        ),
        patch(
            "app.services.pass_service._check_passes",
            new_callable=AsyncMock,
            return_value={"allowed": True, "reason": "pass", "pass_name": "Day All"},
        ),
    ):
        result = await check_tool_access(_user(), "uppercase", "local", db)
    assert result["reason"] == "pass"
    db.commit.assert_awaited_once()


async def test_check_tool_access_falls_back_to_credits():
    db = _db()
    with (
        patch(
            "app.services.pass_service.get_subscription_tier",
            new_callable=AsyncMock,
            return_value="free",
        ),
        patch(
            "app.services.pass_service._check_passes",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.pass_service._check_credits",
            new_callable=AsyncMock,
            return_value={
                "allowed": True,
                "reason": "credit",
                "credits_remaining": 4,
            },
        ),
    ):
        result = await check_tool_access(
            _user(), "uppercase", "local", db, auto_commit=False
        )
    assert result["reason"] == "credit"
    db.commit.assert_not_awaited()


async def test_check_tool_access_daily_limit_message_includes_bonus():
    """With today's login bonus the daily cap is FREE_USES + BONUS (4)."""
    db = _db()
    with (
        patch(
            "app.services.pass_service.get_subscription_tier",
            new_callable=AsyncMock,
            return_value="free",
        ),
        patch(
            "app.services.pass_service._check_passes",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.pass_service._check_credits",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.pass_service.has_logged_in_today",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.services.pass_service._check_daily_limit",
            new_callable=AsyncMock,
            return_value={
                "allowed": False,
                "reason": "blocked",
                "uses_today": 4,
                "max_free": 4,
            },
        ) as mock_limit,
    ):
        result = await check_tool_access(_user(), "uppercase", "local", db)
    assert result["allowed"] is False
    assert "4 uses" in result["message"]
    assert mock_limit.await_args.args[3] == 4  # daily_limit includes the bonus


async def test_check_tool_access_defensive_fallback_blocks():
    db = _db()
    with (
        patch(
            "app.services.pass_service.get_subscription_tier",
            new_callable=AsyncMock,
            return_value="free",
        ),
        patch(
            "app.services.pass_service._check_passes",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.pass_service._check_credits",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.pass_service.has_logged_in_today",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.pass_service._check_daily_limit",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result = await check_tool_access(_user(), "uppercase", "local", db)
    assert result["allowed"] is False
    assert result["reason"] == "blocked"


# ── _check_passes ─────────────────────────────────────────────────────────────


async def test_check_passes_returns_none_without_candidates():
    db = _db([_result(all_rows=[])])
    assert await _check_passes(_user(), "uppercase", db) is None


async def test_check_passes_skips_pass_not_covering_tool():
    p = SimpleNamespace(
        id=uuid.uuid4(),
        pass_id="quick_fix",
        tools_count=1,
        tools=[SimpleNamespace(tool_id="word_count")],
    )
    db = _db([_result(all_rows=[p])])
    assert await _check_passes(_user(), "uppercase", db) is None


async def test_check_passes_consumes_wildcard_pass():
    p = SimpleNamespace(id=uuid.uuid4(), pass_id="day_all", tools_count=-1, tools=[])
    db = _db([_result(all_rows=[p]), _result(scalar_one_or_none=p.id)])
    result = await _check_passes(_user(), "uppercase", db)
    assert result == {"allowed": True, "reason": "pass", "pass_name": "Day All"}


async def test_check_passes_uses_raw_pass_id_when_not_in_catalog():
    p = SimpleNamespace(
        id=uuid.uuid4(),
        pass_id="legacy_pass",
        tools_count=1,
        tools=[SimpleNamespace(tool_id="uppercase")],
    )
    db = _db([_result(all_rows=[p]), _result(scalar_one_or_none=p.id)])
    result = await _check_passes(_user(), "uppercase", db)
    assert result["pass_name"] == "legacy_pass"


async def test_check_passes_returns_none_when_cap_reached():
    p = SimpleNamespace(id=uuid.uuid4(), pass_id="day_all", tools_count=-1, tools=[])
    db = _db([_result(all_rows=[p]), _result(scalar_one_or_none=None)])
    assert await _check_passes(_user(), "uppercase", db) is None


# ── _check_credits ────────────────────────────────────────────────────────────


async def test_check_credits_consumes_and_reports_balance():
    db = _db([_result(scalar_one_or_none=uuid.uuid4())])
    with patch(
        "app.services.pass_service.get_credit_balance",
        new_callable=AsyncMock,
        return_value=4,
    ):
        result = await _check_credits(_user(), db)
    assert result == {"allowed": True, "reason": "credit", "credits_remaining": 4}


async def test_check_credits_returns_none_without_balance():
    db = _db([_result(scalar_one_or_none=None)])
    assert await _check_credits(_user(), db) is None


# ── check_visitor_access ──────────────────────────────────────────────────────


async def test_check_visitor_access_always_free_tool():
    db = _db()
    result = await check_visitor_access("fp", "1.2.3.4", "compare", "local", db)
    assert result == {"allowed": True, "reason": "free"}
    db.execute.assert_not_awaited()


async def test_check_visitor_access_existing_visitor_allowed_updates_identity():
    visitor = SimpleNamespace(
        id=uuid.uuid4(), fingerprint="old-fp", ip_address="9.9.9.9"
    )
    db = _db([_result(first=visitor)])
    with patch(
        "app.services.pass_service._check_daily_limit",
        new_callable=AsyncMock,
        return_value={"allowed": True, "reason": "free", "uses_today": 2},
    ):
        result = await check_visitor_access(
            "new-fp", "1.2.3.4", "uppercase", "local", db
        )
    assert result["allowed"] is True
    assert visitor.fingerprint == "new-fp"
    assert visitor.ip_address == "1.2.3.4"
    db.commit.assert_awaited_once()


async def test_check_visitor_access_existing_visitor_blocked_gets_message():
    visitor = SimpleNamespace(id=uuid.uuid4(), fingerprint="fp", ip_address="1.2.3.4")
    db = _db([_result(first=visitor)])
    with patch(
        "app.services.pass_service._check_daily_limit",
        new_callable=AsyncMock,
        return_value={
            "allowed": False,
            "reason": "blocked",
            "uses_today": 3,
            "max_free": 3,
        },
    ):
        result = await check_visitor_access("fp", "1.2.3.4", "uppercase", "local", db)
    assert result["allowed"] is False
    assert "sign in" in result["message"].lower()


async def test_check_visitor_access_new_visitor_created_and_counted():
    db = _db([_result(first=None)])
    with patch(
        "app.services.pass_service.increment_visitor_tool_usage",
        new_callable=AsyncMock,
        return_value=1,
    ) as mock_inc:
        result = await check_visitor_access(
            "fresh-fp", "1.2.3.4", "uppercase", "local", db
        )
    assert result == {"allowed": True, "reason": "free", "uses_today": 1}
    added = db.add.call_args.args[0]
    assert isinstance(added, VisitorUsage)
    assert added.fingerprint == "fresh-fp"
    mock_inc.assert_awaited_once()
    db.commit.assert_awaited_once()


# ── Grants ────────────────────────────────────────────────────────────────────


async def test_grant_pass_unknown_pass_raises_value_error():
    from app.services.pass_service import grant_pass

    with pytest.raises(ValueError, match="Unknown pass"):
        await grant_pass(_user(), "no_such_pass", [], "spin", _db())


async def test_grant_pass_all_tools_pass_stores_wildcard():
    from app.services.pass_service import grant_pass

    db = _db()
    billing_pass = await grant_pass(
        _user(), "day_all", ["uppercase", "word_count"], "spin", db
    )
    assert isinstance(billing_pass, BillingUserPass)
    assert billing_pass.tools_count == -1
    assert billing_pass.uses_per_day == 50
    tool_rows = [
        c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], UserPassTool)
    ]
    assert [t.tool_id for t in tool_rows] == ["*"]
    db.commit.assert_awaited_once()


async def test_grant_pass_single_tool_pass_stores_selected_tool():
    from app.services.pass_service import grant_pass

    db = _db()
    billing_pass = await grant_pass(
        _user(),
        "quick_fix",
        ["uppercase"],
        "razorpay",
        db,
        razorpay_payment_id="pay_1",
        auto_commit=False,
    )
    assert billing_pass.razorpay_payment_id == "pay_1"
    tool_rows = [
        c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], UserPassTool)
    ]
    assert [t.tool_id for t in tool_rows] == ["uppercase"]
    db.commit.assert_not_awaited()


# ── Welcome gift ──────────────────────────────────────────────────────────────


async def test_welcome_gift_granted_on_first_purchase():
    db = _db([_result(scalar=0)])
    granted = await maybe_grant_welcome_gift(_user(), db)
    assert granted is True
    added = db.add.call_args.args[0]
    assert isinstance(added, BillingUserCredit)
    assert added.source == "welcome"
    assert added.credits_total == 10


async def test_welcome_gift_skipped_when_already_granted():
    db = _db([_result(scalar=1)])
    assert await maybe_grant_welcome_gift(_user(), db) is False
    db.add.assert_not_called()


# ── Balances and active rows ──────────────────────────────────────────────────


async def test_get_credit_balance_returns_sum():
    db = _db([_result(scalar=7)])
    assert await get_credit_balance(_user(), db) == 7


async def test_get_active_passes_returns_rows():
    rows = [SimpleNamespace(pass_id="day_all")]
    db = _db([_result(all_rows=rows)])
    assert await get_active_passes(_user(), db) == rows


async def test_get_active_credits_returns_rows():
    rows = [SimpleNamespace(credits_remaining=3)]
    db = _db([_result(all_rows=rows)])
    assert await get_active_credits(_user(), db) == rows


# ── Daily login ───────────────────────────────────────────────────────────────


async def test_record_daily_login_first_of_day_returns_true():
    db = _db([_result(rowcount=1)])
    assert await record_daily_login(_user(), db) is True
    db.commit.assert_awaited_once()


async def test_record_daily_login_repeat_returns_false():
    db = _db([_result(rowcount=0)])
    assert await record_daily_login(_user(), db) is False


# ── Spin the wheel ────────────────────────────────────────────────────────────


async def test_spin_wheel_rejects_second_spin_in_week():
    db = _db([_result(first=SimpleNamespace(id=uuid.uuid4()))])
    result = await spin_wheel(_user(), db)
    assert "error" in result
    assert "already spun" in result["error"].lower()


async def test_spin_wheel_grants_credit_reward():
    db = _db([_result(first=None)])
    with patch(
        "app.services.pass_service.secrets.randbelow", return_value=0
    ):  # roll=1 → 1 credit
        result = await spin_wheel(_user(), db)
    assert result["reward_type"] == "credits"
    assert result["amount"] == 1
    credit_rows = [
        c.args[0]
        for c in db.add.call_args_list
        if isinstance(c.args[0], BillingUserCredit)
    ]
    assert len(credit_rows) == 1
    assert credit_rows[0].source == "spin"
    db.commit.assert_awaited_once()


async def test_spin_wheel_grants_pass_reward():
    db = _db([_result(first=None)])
    with patch(
        "app.services.pass_service.secrets.randbelow", return_value=60
    ):  # roll=61 → quick_fix pass
        result = await spin_wheel(_user(), db)
    assert result["reward_type"] == "pass"
    assert result["pass_id"] == "quick_fix"
    assert result["pass_name"] == "Quick Fix"
    pass_rows = [
        c.args[0]
        for c in db.add.call_args_list
        if isinstance(c.args[0], BillingUserPass)
    ]
    assert len(pass_rows) == 1
    assert pass_rows[0].source == "spin"


async def test_spin_wheel_race_on_weekly_unique_returns_friendly_error():
    db = _db([_result(first=None)])
    db.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    result = await spin_wheel(_user(), db)
    assert "error" in result
    db.rollback.assert_awaited_once()


# ── Referral code ─────────────────────────────────────────────────────────────


async def test_ensure_referral_code_returns_existing():
    db = _db()
    assert await ensure_referral_code(_user(referral_code="KEEPME1234"), db) == (
        "KEEPME1234"
    )
    db.commit.assert_not_awaited()


async def test_ensure_referral_code_generates_and_commits():
    db = _db()
    user = _user(referral_code=None)
    code = await ensure_referral_code(user, db)
    assert code == user.referral_code
    assert 1 <= len(code) <= 10
    assert code == code.upper()
    db.commit.assert_awaited_once()


# ── Claim referral ────────────────────────────────────────────────────────────


async def test_claim_referral_rejects_second_claim():
    user = _user(referred_by=uuid.uuid4())
    db = _db([_result(first=user)])
    result = await claim_referral(user, "SOMECODE", db)
    assert "already used" in result["error"]


async def test_claim_referral_rejects_own_code():
    user = _user(referral_code="MYCODE1234")
    db = _db([_result(first=user)])
    result = await claim_referral(user, "MYCODE1234", db)
    assert "own referral code" in result["error"]


async def test_claim_referral_requires_verified_email():
    user = _user(is_email_verified=False)
    db = _db([_result(first=user)])
    result = await claim_referral(user, "FRIENDCODE", db)
    assert "verify" in result["error"].lower()


async def test_claim_referral_rejects_unknown_code():
    user = _user()
    db = _db([_result(first=user), _result(first=None)])
    result = await claim_referral(user, "NOSUCHCODE", db)
    assert "invalid" in result["error"].lower()


async def test_claim_referral_rewards_both_parties():
    user = _user()
    referrer = _user(referral_code="FRIENDCODE")
    db = _db([_result(first=user), _result(first=referrer)], scalar=0)
    with (
        patch(
            "app.services.pass_service.grant_pass", new_callable=AsyncMock
        ) as mock_pass,
        patch(
            "app.services.pass_service.grant_credits", new_callable=AsyncMock
        ) as mock_credits,
    ):
        result = await claim_referral(user, "FRIENDCODE", db)
    assert result["success"] is True
    assert user.referred_by == referrer.id
    mock_pass.assert_awaited_once()  # referrer pass reward
    assert mock_credits.await_count == 2  # referrer + new user credits
    db.commit.assert_awaited_once()


async def test_claim_referral_referrer_over_cap_earns_nothing():
    """Past REFERRAL_MAX_PER_REFERRER the new user is still rewarded but the
    referrer gets no payout (M-10 anti-farming)."""
    user = _user()
    referrer = _user(referral_code="FRIENDCODE")
    db = _db([_result(first=user), _result(first=referrer)], scalar=20)
    with (
        patch(
            "app.services.pass_service.grant_pass", new_callable=AsyncMock
        ) as mock_pass,
        patch(
            "app.services.pass_service.grant_credits", new_callable=AsyncMock
        ) as mock_credits,
    ):
        result = await claim_referral(user, "FRIENDCODE", db)
    assert result["success"] is True
    mock_pass.assert_not_awaited()
    mock_credits.assert_awaited_once()  # new-user reward only
    assert mock_credits.await_args.args[0] is user


async def test_claim_referral_rolls_back_on_grant_failure():
    user = _user()
    referrer = _user(referral_code="FRIENDCODE")
    db = _db([_result(first=user), _result(first=referrer)], scalar=0)
    with (
        patch(
            "app.services.pass_service.grant_pass",
            new_callable=AsyncMock,
            side_effect=RuntimeError("insert failed"),
        ),
        pytest.raises(RuntimeError),
    ):
        await claim_referral(user, "FRIENDCODE", db)
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
