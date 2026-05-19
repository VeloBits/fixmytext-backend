"""Tests for app/services/payment_service.py — payment verification logic."""

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from tests.conftest import make_user


@pytest.mark.asyncio
async def test_verify_payment_invalid_signature():
    """Invalid signature raises HTTPException(400)."""
    from app.services.payment_service import verify_razorpay_payment

    user = make_user()

    with patch(
        "app.services.payment_service.verify_payment_signature", return_value=False
    ):
        with pytest.raises(HTTPException) as exc_info:
            await verify_razorpay_payment("order_1", "pay_1", "bad_sig", user)
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_payment_fetch_order_fails():
    """Failed fetch_order raises HTTPException(502)."""
    from app.services.payment_service import verify_razorpay_payment

    user = make_user()

    with (
        patch(
            "app.services.payment_service.verify_payment_signature", return_value=True
        ),
        patch(
            "app.services.payment_service.fetch_order", side_effect=Exception("network")
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await verify_razorpay_payment("order_1", "pay_1", "sig", user)
        assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_verify_payment_wrong_user():
    """Order belonging to another user raises HTTPException(400)."""
    from app.services.payment_service import verify_razorpay_payment

    user = make_user()

    order = {"notes": {"user_id": str(uuid.uuid4())}}  # different user

    with (
        patch(
            "app.services.payment_service.verify_payment_signature", return_value=True
        ),
        patch("app.services.payment_service.fetch_order", return_value=order),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await verify_razorpay_payment("order_1", "pay_1", "sig", user)
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_payment_success():
    """Valid signature and matching user returns order dict."""
    from app.services.payment_service import verify_razorpay_payment

    user = make_user()

    order = {"notes": {"user_id": str(user.id)}, "amount": 10000, "currency": "INR"}

    with (
        patch(
            "app.services.payment_service.verify_payment_signature", return_value=True
        ),
        patch("app.services.payment_service.fetch_order", return_value=order),
    ):
        result = await verify_razorpay_payment("order_1", "pay_1", "sig", user)
        assert result == order
