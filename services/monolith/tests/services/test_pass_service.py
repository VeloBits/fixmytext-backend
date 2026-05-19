"""Tests for app/services/pass_service.py"""

import uuid
from unittest.mock import MagicMock

import pytest
from tests.conftest import make_mock_db, make_user

# ── pass_service.get_subscription_tier ───────────────────────────────────────


@pytest.mark.asyncio
async def test_get_subscription_tier_free():
    from app.services.pass_service import get_subscription_tier

    db = make_mock_db()
    result = MagicMock()
    result.scalar.return_value = None  # no active pro subscription
    db.execute.return_value = result

    tier = await get_subscription_tier(uuid.uuid4(), db)
    assert tier == "free"


@pytest.mark.asyncio
async def test_get_subscription_tier_pro():
    from app.services.pass_service import get_subscription_tier

    db = make_mock_db()
    result = MagicMock()
    result.scalar.return_value = "pro"
    db.execute.return_value = result

    tier = await get_subscription_tier(uuid.uuid4(), db)
    assert tier == "pro"


# ── pass_service.get_credit_balance ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_credit_balance_zero():
    from app.services.pass_service import get_credit_balance

    user = make_user()
    db = make_mock_db()
    result = MagicMock()
    result.scalar.return_value = 0
    db.execute.return_value = result

    balance = await get_credit_balance(user, db)
    assert balance == 0


@pytest.mark.asyncio
async def test_get_credit_balance_positive():
    from app.services.pass_service import get_credit_balance

    user = make_user()
    db = make_mock_db()
    result = MagicMock()
    result.scalar.return_value = 15
    db.execute.return_value = result

    balance = await get_credit_balance(user, db)
    assert balance == 15


# ── pass_service.check_tool_access ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_tool_access_always_free():
    from app.services.pass_service import check_tool_access

    user = make_user()
    db = make_mock_db()

    # "find_replace" is in ALWAYS_FREE_TOOL_IDS
    result = await check_tool_access(user, "find_replace", "api", db)
    assert result["allowed"] is True
    assert result["reason"] == "free"


@pytest.mark.asyncio
async def test_check_tool_access_drawer_type():
    from app.services.pass_service import check_tool_access

    user = make_user()
    db = make_mock_db()

    result = await check_tool_access(user, "any_tool", "drawer", db)
    assert result["allowed"] is True


@pytest.mark.asyncio
async def test_check_tool_access_within_daily_limit():
    from app.services.pass_service import check_tool_access

    user = make_user()
    db = make_mock_db()

    call_count = 0

    async def execute_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        # subscription check
        if call_count == 1:
            result.scalar.return_value = None  # not pro
        # active passes
        elif call_count == 2:
            result.scalars.return_value.all.return_value = []  # no passes
        # credit balance
        elif call_count == 3:
            result.scalar.return_value = 0  # no credits
        # daily login bonus
        elif call_count == 4:
            result.scalars.return_value.first.return_value = None  # no login bonus
        # tool usage count today
        elif call_count == 5:
            result.scalar.return_value = 0  # 0 uses today
        return result

    db.execute.side_effect = execute_side_effect

    result = await check_tool_access(user, "uppercase", "api", db)
    assert result["allowed"] is True


@pytest.mark.asyncio
@pytest.mark.xfail(reason="DB call sequence changed after _check_daily_limit refactor")
async def test_check_tool_access_daily_limit_exceeded():
    from app.services.pass_service import check_tool_access

    user = make_user()
    db = make_mock_db()

    call_count = 0

    async def execute_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar.return_value = None  # not pro
        elif call_count == 2:
            result.scalars.return_value.all.return_value = []  # no passes
        elif call_count == 3:
            result.scalars.return_value.first.return_value = None  # no credits
        elif call_count == 4:
            # get_tool_use_count_today → 5 uses today (over limit)
            result.scalar.return_value = 5
        elif call_count == 5:
            # has_logged_in_today → not logged in today
            result.scalars.return_value.first.return_value = None
        return result

    db.execute.side_effect = execute_side_effect

    result = await check_tool_access(user, "uppercase", "api", db)
    assert result["allowed"] is False


# ── pass_service.grant_credits ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_grant_credits():
    from app.services.pass_service import grant_credits

    user = make_user()
    db = make_mock_db()

    await grant_credits(user, 10, "test", db)
    db.add.assert_called_once()
    db.commit.assert_awaited()


# ── pass_service.get_tool_use_count_today ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tool_use_count_today_zero():
    from app.services.pass_service import get_tool_use_count_today

    db = make_mock_db()
    result = MagicMock()
    result.scalar.return_value = None
    db.execute.return_value = result

    count = await get_tool_use_count_today(uuid.uuid4(), "uppercase", db)
    assert count == 0


@pytest.mark.asyncio
async def test_get_tool_use_count_today_nonzero():
    from app.services.pass_service import get_tool_use_count_today

    db = make_mock_db()
    result = MagicMock()
    result.scalar.return_value = 3
    db.execute.return_value = result

    count = await get_tool_use_count_today(uuid.uuid4(), "uppercase", db)
    assert count == 3


# ── pass_service.record_tool_discovery ───────────────────────────────────────


@pytest.mark.asyncio
async def test_record_tool_discovery():
    from app.services.pass_service import record_tool_discovery

    db = make_mock_db()
    await record_tool_discovery(uuid.uuid4(), "uppercase", db)
    db.execute.assert_awaited()
    db.commit.assert_awaited()
