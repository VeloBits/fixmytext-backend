"""Tests for app/services/razorpay_service.py"""

import hashlib
import hmac
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services import razorpay_service
from app.services.razorpay_service import (
    PRO_PLAN_PRICES,
    create_order,
    fetch_order,
    get_client,
    init_razorpay,
    verify_payment_signature,
    verify_webhook_signature,
)

# ── verify_webhook_signature ──────────────────────────────────────────────────


def test_verify_webhook_signature_correct():
    original_secret = settings.RAZORPAY_WEBHOOK_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = "test-secret"  # noqa: S105
    try:
        body = b'{"event": "payment.captured"}'
        expected = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        result = verify_webhook_signature(body, expected)
        assert result is True
    finally:
        settings.RAZORPAY_WEBHOOK_SECRET = original_secret


def test_verify_webhook_signature_wrong():
    original_secret = settings.RAZORPAY_WEBHOOK_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = "test-secret"  # noqa: S105
    try:
        body = b'{"event": "payment.captured"}'
        result = verify_webhook_signature(body, "wrong-signature")
        assert result is False
    finally:
        settings.RAZORPAY_WEBHOOK_SECRET = original_secret


def test_verify_webhook_signature_no_secret():
    original_secret = settings.RAZORPAY_WEBHOOK_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = ""
    try:
        result = verify_webhook_signature(b"body", "sig")
        assert result is False
    finally:
        settings.RAZORPAY_WEBHOOK_SECRET = original_secret


def test_verify_payment_signature_invalid():
    # Without a real client, this will raise RuntimeError
    with pytest.raises((RuntimeError, Exception)):
        verify_payment_signature("order_id", "pay_id", "bad_sig")


def test_get_client_raises_when_not_initialized():
    original_client = razorpay_service._client
    razorpay_service._client = None
    try:
        with pytest.raises(RuntimeError, match="not initialized"):
            get_client()
    finally:
        razorpay_service._client = original_client


# ── init_razorpay ──────────────────────────────────────────────────────────


def test_init_razorpay_no_key():
    """init_razorpay does nothing when RAZORPAY_KEY_ID is empty."""
    original_key = settings.RAZORPAY_KEY_ID
    original_client = razorpay_service._client
    settings.RAZORPAY_KEY_ID = ""
    razorpay_service._client = None
    try:
        init_razorpay()
        assert razorpay_service._client is None
    finally:
        settings.RAZORPAY_KEY_ID = original_key
        razorpay_service._client = original_client


def test_init_razorpay_with_key():
    """init_razorpay creates a client when key is set."""
    original_key = settings.RAZORPAY_KEY_ID
    original_secret = settings.RAZORPAY_KEY_SECRET
    original_client = razorpay_service._client
    settings.RAZORPAY_KEY_ID = "rzp_test_key"  # noqa: S105
    settings.RAZORPAY_KEY_SECRET = "rzp_test_secret"  # noqa: S105
    try:
        init_razorpay()
        assert razorpay_service._client is not None
    finally:
        settings.RAZORPAY_KEY_ID = original_key
        settings.RAZORPAY_KEY_SECRET = original_secret
        razorpay_service._client = original_client


# ── create_order ──────────────────────────────────────────────────────────


def test_create_order_basic():
    """create_order calls Razorpay API with correct params."""
    mock_client = MagicMock()
    mock_client.order.create.return_value = {
        "id": "order_new",
        "amount": 500,
        "currency": "USD",
    }

    original_client = razorpay_service._client
    razorpay_service._client = mock_client
    try:
        result = create_order(
            amount=500,
            currency="usd",
            receipt="receipt_test",
            notes={"user_id": "123"},
        )
    finally:
        razorpay_service._client = original_client

    assert result["id"] == "order_new"
    mock_client.order.create.assert_called_once()
    call_args = mock_client.order.create.call_args[0][0]
    assert call_args["amount"] == 500
    assert call_args["currency"] == "USD"


def test_create_order_returns_existing_on_idempotency():
    """create_order returns existing unpaid order when idempotency key matches."""
    existing_order = {
        "id": "order_existing",
        "status": "created",
        "amount": 500,
        "currency": "USD",
    }
    mock_client = MagicMock()
    mock_client.order.all.return_value = {"items": [existing_order]}

    original_client = razorpay_service._client
    razorpay_service._client = mock_client
    try:
        result = create_order(
            amount=500,
            currency="usd",
            receipt="receipt_test",
            notes={"user_id": "123"},
            idempotency_key="pro_123",
        )
    finally:
        razorpay_service._client = original_client

    assert result["id"] == "order_existing"
    mock_client.order.create.assert_not_called()


def test_create_order_idempotency_no_match_creates_new():
    """When existing orders don't match, a new order is created."""
    existing_order = {
        "id": "order_old",
        "status": "paid",  # not "created"
        "amount": 500,
        "currency": "USD",
    }
    mock_client = MagicMock()
    mock_client.order.all.return_value = {"items": [existing_order]}
    mock_client.order.create.return_value = {
        "id": "order_new",
        "amount": 500,
        "currency": "USD",
    }

    original_client = razorpay_service._client
    razorpay_service._client = mock_client
    try:
        result = create_order(
            amount=500,
            currency="usd",
            receipt="receipt_test",
            notes={"user_id": "123"},
            idempotency_key="pro_123",
        )
    finally:
        razorpay_service._client = original_client

    assert result["id"] == "order_new"
    mock_client.order.create.assert_called_once()


def test_create_order_idempotency_check_failure_creates_new():
    """If checking existing orders fails, a new order is created anyway."""
    mock_client = MagicMock()
    mock_client.order.all.side_effect = RuntimeError("API error")
    mock_client.order.create.return_value = {
        "id": "order_new",
        "amount": 500,
        "currency": "USD",
    }

    original_client = razorpay_service._client
    razorpay_service._client = mock_client
    try:
        result = create_order(
            amount=500,
            currency="usd",
            receipt="receipt_test",
            notes={"user_id": "123"},
            idempotency_key="pro_123",
        )
    finally:
        razorpay_service._client = original_client

    assert result["id"] == "order_new"


# ── fetch_order ────────────────────────────────────────────────────────────


def test_fetch_order():
    """fetch_order delegates to Razorpay client."""
    mock_client = MagicMock()
    mock_client.order.fetch.return_value = {"id": "order_x", "status": "paid"}

    original_client = razorpay_service._client
    razorpay_service._client = mock_client
    try:
        result = fetch_order("order_x")
    finally:
        razorpay_service._client = original_client

    assert result["id"] == "order_x"
    mock_client.order.fetch.assert_called_once_with("order_x")


# ── verify_payment_signature ───────────────────────────────────────────────


def test_verify_payment_signature_valid():
    """Valid signature returns True."""
    mock_client = MagicMock()
    mock_client.utility.verify_payment_signature.return_value = None

    original_client = razorpay_service._client
    razorpay_service._client = mock_client
    try:
        result = verify_payment_signature("order_x", "pay_x", "sig_x")
    finally:
        razorpay_service._client = original_client

    assert result is True


def test_verify_payment_signature_raises_on_invalid():
    """Invalid signature returns False."""
    import razorpay

    mock_client = MagicMock()
    mock_client.utility.verify_payment_signature.side_effect = (
        razorpay.errors.SignatureVerificationError("bad sig")
    )

    original_client = razorpay_service._client
    razorpay_service._client = mock_client
    try:
        result = verify_payment_signature("order_x", "pay_x", "bad_sig")
    finally:
        razorpay_service._client = original_client

    assert result is False


# ── PRO_PLAN_PRICES ────────────────────────────────────────────────────────


def test_pro_plan_prices_contains_expected_regions():
    """PRO_PLAN_PRICES has all expected regions."""
    assert set(PRO_PLAN_PRICES.keys()) == {"IN", "US", "GB", "EU"}
    for _region, pricing in PRO_PLAN_PRICES.items():
        assert "amount" in pricing
        assert "currency" in pricing
        assert isinstance(pricing["amount"], int)
