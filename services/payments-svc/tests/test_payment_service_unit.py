"""Unit tests for app.services.payment_service.verify_razorpay_payment.

Pins the three-step trust chain: cryptographic signature check, order
re-fetch from Razorpay, and JWT-identity ownership check against the
server-set order notes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.payment_service import verify_razorpay_payment


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


@pytest.mark.asyncio
async def test_invalid_signature_raises_400():
    with (
        patch(
            "app.services.payment_service.verify_payment_signature",
            return_value=False,
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await verify_razorpay_payment("order_1", "pay_1", "bad-sig", _user())
    assert exc.value.status_code == 400
    assert "invalid signature" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_order_fetch_failure_raises_502():
    with (
        patch(
            "app.services.payment_service.verify_payment_signature",
            return_value=True,
        ),
        patch(
            "app.services.payment_service.fetch_order",
            side_effect=RuntimeError("razorpay down"),
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await verify_razorpay_payment("order_1", "pay_1", "sig", _user())
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_order_owned_by_other_user_raises_400():
    order = {"notes": {"user_id": str(uuid.uuid4())}}
    with (
        patch(
            "app.services.payment_service.verify_payment_signature",
            return_value=True,
        ),
        patch("app.services.payment_service.fetch_order", return_value=order),
        pytest.raises(HTTPException) as exc,
    ):
        await verify_razorpay_payment("order_1", "pay_1", "sig", _user())
    assert exc.value.status_code == 400
    assert "does not belong" in exc.value.detail


@pytest.mark.asyncio
async def test_valid_payment_returns_order():
    user = _user()
    order = {"id": "order_1", "notes": {"user_id": str(user.id)}}
    with (
        patch(
            "app.services.payment_service.verify_payment_signature",
            return_value=True,
        ),
        patch("app.services.payment_service.fetch_order", return_value=order),
    ):
        result = await verify_razorpay_payment("order_1", "pay_1", "sig", user)
    assert result == order
