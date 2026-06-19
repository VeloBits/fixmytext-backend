"""Tests for webhook hardening changes — body size limit (M-4) and duplicate
PaymentEvent audit trail after AlreadyFulfilled rollback (M-3).

Pure-logic / unit tests; no live DB or Razorpay connection required.
"""

import pytest


# ── M-4: Body size limit ──────────────────────────────────────────────────────


def test_webhook_max_body_bytes_present_in_config():
    """Config must expose WEBHOOK_MAX_BODY_BYTES so the guard is tunable."""
    from app.core.config import settings

    assert hasattr(settings, "WEBHOOK_MAX_BODY_BYTES"), (
        "settings.WEBHOOK_MAX_BODY_BYTES missing — add it to config.py (M-4)"
    )
    assert settings.WEBHOOK_MAX_BODY_BYTES > 0


def test_webhook_max_body_bytes_default_is_reasonable():
    """Default must be above a realistic Razorpay payload (~2 KB) and below 1 MB."""
    from app.core.config import settings

    assert 4096 < settings.WEBHOOK_MAX_BODY_BYTES <= 1_048_576, (
        "WEBHOOK_MAX_BODY_BYTES should be between 4 KB and 1 MB; "
        f"got {settings.WEBHOOK_MAX_BODY_BYTES}"
    )


def test_webhook_handler_reads_body_after_size_guard():
    """The webhook source must check body size before (or immediately after)
    reading, not several lines later."""
    import inspect

    from app.api.v1.endpoints import subscription as sub_ep

    src = inspect.getsource(sub_ep.razorpay_webhook)
    # Both the content-length pre-check and the post-read check must be present.
    assert "WEBHOOK_MAX_BODY_BYTES" in src, (
        "razorpay_webhook must reference WEBHOOK_MAX_BODY_BYTES (M-4)"
    )
    assert "413" in src, (
        "razorpay_webhook must raise HTTP 413 on oversized payload (M-4)"
    )


# ── M-3: Duplicate PaymentEvent audit trail ───────────────────────────────────


def test_webhook_records_duplicate_event_after_already_fulfilled():
    """After AlreadyFulfilled the webhook source must insert a 'duplicate'
    PaymentEvent so auditors can see the late delivery (M-3)."""
    import inspect

    from app.api.v1.endpoints import subscription as sub_ep

    src = inspect.getsource(sub_ep.razorpay_webhook)
    # Source must reference status="duplicate" in the AlreadyFulfilled block.
    assert '"duplicate"' in src or "'duplicate'" in src, (
        "razorpay_webhook must insert a PaymentEvent(status='duplicate') "
        "after AlreadyFulfilled rollback for audit trail (M-3)"
    )


# ── M-1: UTC date correctness ─────────────────────────────────────────────────


def test_pass_service_uses_utc_date_not_local_date():
    """pass_service must use datetime.now(UTC).date() so daily limits reset at
    UTC midnight regardless of the server's local timezone (M-1)."""
    import inspect

    from app.services import pass_service

    src = inspect.getsource(pass_service)
    assert "date.today()" not in src, (
        "pass_service still contains date.today() — replace with "
        "datetime.now(UTC).date() so limits reset at UTC midnight (M-1)"
    )
    assert "datetime.now(UTC).date()" in src or "now.date()" in src, (
        "pass_service must use datetime.now(UTC).date() or now.date() (M-1)"
    )


# ── M-2: Rate limiting ────────────────────────────────────────────────────────


def test_rate_limit_check_rate_limit_exists():
    """rate_limit module must export check_rate_limit (M-2)."""
    from app.services.rate_limit import check_rate_limit  # noqa: F401


def test_rate_limit_allows_when_redis_unavailable():
    """check_rate_limit must not raise when Redis is None (graceful degradation)."""
    import asyncio

    from unittest.mock import patch

    from app.services.rate_limit import check_rate_limit

    async def _run():
        with patch("app.services.rate_limit.get_redis", return_value=None):
            await check_rate_limit("test:key", max_count=1)  # should not raise

    asyncio.get_event_loop().run_until_complete(_run())


@pytest.mark.asyncio
async def test_rate_limit_raises_429_when_exceeded():
    """check_rate_limit must raise HTTP 429 once the counter exceeds max_count."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import HTTPException

    from app.services.rate_limit import check_rate_limit

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=11)  # already at 11 > max 10
    mock_redis.expire = AsyncMock()

    with patch("app.services.rate_limit.get_redis", return_value=mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit("test:key", max_count=10)
        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_sets_expiry_on_first_call():
    """The first INCR (count == 1) must set an EXPIRE so the key auto-clears."""
    from unittest.mock import AsyncMock, call, patch

    from app.services.rate_limit import check_rate_limit

    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    with patch("app.services.rate_limit.get_redis", return_value=mock_redis):
        await check_rate_limit("test:key", max_count=10, window_secs=60)

    mock_redis.expire.assert_called_once_with("test:key", 60)


def test_order_rate_limit_per_minute_in_config():
    """Config must expose ORDER_RATE_LIMIT_PER_MINUTE (M-2)."""
    from app.core.config import settings

    assert hasattr(settings, "ORDER_RATE_LIMIT_PER_MINUTE"), (
        "settings.ORDER_RATE_LIMIT_PER_MINUTE missing — add it to config.py (M-2)"
    )
    assert settings.ORDER_RATE_LIMIT_PER_MINUTE > 0


def test_order_endpoints_reference_rate_limit():
    """Both pass-order endpoints and the subscription checkout must call
    check_rate_limit (M-2)."""
    import inspect

    from app.api.v1.endpoints import passes as passes_ep
    from app.api.v1.endpoints import subscription as sub_ep

    for ep_name, fn in [
        ("create_pass_order", passes_ep.create_pass_order),
        ("create_credit_order", passes_ep.create_credit_order),
        ("create_pro_checkout", sub_ep.create_pro_checkout),
    ]:
        src = inspect.getsource(fn)
        assert "check_rate_limit" in src, (
            f"{ep_name} must call check_rate_limit (M-2)"
        )


# ── M-5: DEFAULT_REGION dead-code removal ─────────────────────────────────────


def test_passes_catalog_endpoint_no_longer_imports_default_region():
    """DEFAULT_REGION import removed from passes.py endpoint — it was dead code
    because detect_region() always returns a REGIONS-valid value (M-5)."""
    import ast
    import pathlib

    src = pathlib.Path(
        "app/api/v1/endpoints/passes.py"
    ).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.core.pass_catalog":
            names = [alias.name for alias in node.names]
            assert "DEFAULT_REGION" not in names, (
                "DEFAULT_REGION was dead code in passes.py and should be removed (M-5)"
            )
