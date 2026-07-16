"""Unit tests for app.services.razorpay_service.

Covers both backends: the in-memory fake (PAYMENTS_BACKEND=fake, used by E2E
tests) and the real client path with a mocked razorpay.Client — order
creation with idempotent receipt reuse, receipt truncation (B-5), order
fetch, and payment/webhook signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from unittest.mock import MagicMock, patch

import pytest
import razorpay

import app.services.razorpay_service as rz
from app.core.config import settings

# ── payments_configured ───────────────────────────────────────────────────────


def test_payments_configured_true_in_fake_mode(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "fake")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    assert rz.payments_configured() is True


def test_payments_configured_true_with_real_key(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_key")
    assert rz.payments_configured() is True


def test_payments_configured_false_without_key_or_fake(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    assert rz.payments_configured() is False


# ── Fake backend ──────────────────────────────────────────────────────────────


def test_fake_create_order_and_fetch_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "fake")
    monkeypatch.setattr(rz, "_fake_orders", {})

    order = rz.create_order(
        amount=500,
        currency="inr",
        receipt="rcpt_1",
        notes={"user_id": "u1"},
        idempotency_key="credit_credits_5_u1",
    )
    assert order["id"].startswith("order_fake_")
    assert order["amount"] == 500
    assert order["currency"] == "INR"
    assert order["status"] == "created"
    assert rz.fetch_order(order["id"]) == order


def test_fake_fetch_order_unknown_id_raises(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "fake")
    monkeypatch.setattr(rz, "_fake_orders", {})
    with pytest.raises(RuntimeError, match="not found"):
        rz.fetch_order("order_fake_missing")


def test_fake_verify_payment_signature_valid_and_invalid(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "fake")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "fake-secret")

    good = hmac.new(b"fake-secret", b"order_1|pay_1", hashlib.sha256).hexdigest()
    assert rz.verify_payment_signature("order_1", "pay_1", good) is True
    assert rz.verify_payment_signature("order_1", "pay_1", "bad-sig") is False


# ── init_razorpay / get_client ────────────────────────────────────────────────


def test_init_razorpay_noop_in_fake_mode(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "fake")
    monkeypatch.setattr(rz, "_client", None)
    rz.init_razorpay()
    assert rz._client is None


def test_init_razorpay_noop_without_key(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(rz, "_client", None)
    rz.init_razorpay()
    assert rz._client is None


def test_init_razorpay_creates_client_with_key(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "rzp_test_secret")
    monkeypatch.setattr(rz, "_client", None)
    with patch("razorpay.Client") as mock_client_cls:
        rz.init_razorpay()
        assert rz.get_client() is mock_client_cls.return_value
    mock_client_cls.assert_called_once_with(auth=("rzp_test_key", "rzp_test_secret"))


def test_get_client_raises_when_uninitialized(monkeypatch):
    monkeypatch.setattr(rz, "_client", None)
    with pytest.raises(RuntimeError, match="not initialized"):
        rz.get_client()


# ── Real backend: create_order ────────────────────────────────────────────────


def _real_mode(monkeypatch) -> MagicMock:
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_key")
    client = MagicMock()
    monkeypatch.setattr(rz, "_client", client)
    return client


def test_create_order_reuses_existing_pending_order(monkeypatch):
    client = _real_mode(monkeypatch)
    existing = {
        "id": "order_existing",
        "status": "created",
        "amount": 500,
        "currency": "INR",
    }
    client.order.all.return_value = {"items": [existing]}

    order = rz.create_order(
        amount=500,
        currency="inr",
        receipt="rcpt",
        notes={},
        idempotency_key="key_1",
    )
    assert order == existing
    client.order.create.assert_not_called()


def test_create_order_creates_new_and_truncates_receipt(monkeypatch):
    """Idempotency keys longer than 40 chars must be truncated (B-5)."""
    client = _real_mode(monkeypatch)
    client.order.all.return_value = {"items": []}
    client.order.create.return_value = {
        "id": "order_new",
        "amount": 1000,
        "currency": "INR",
    }
    long_key = f"pass_day_single_{uuid.uuid4()}"  # 52 chars
    assert len(long_key) > 40

    order = rz.create_order(
        amount=1000,
        currency="inr",
        receipt="rcpt",
        notes={"a": "b"},
        idempotency_key=long_key,
    )
    assert order["id"] == "order_new"
    created = client.order.create.call_args.args[0]
    assert created["receipt"] == long_key[:40]
    assert len(created["receipt"]) == 40
    assert created["currency"] == "INR"
    assert created["notes"] == {"a": "b"}


def test_create_order_lookup_failure_falls_back_to_create(monkeypatch):
    client = _real_mode(monkeypatch)
    client.order.all.side_effect = RuntimeError("listing failed")
    client.order.create.return_value = {"id": "order_fallback"}

    order = rz.create_order(
        amount=200,
        currency="inr",
        receipt="rcpt",
        notes={},
        idempotency_key="key_2",
    )
    assert order["id"] == "order_fallback"


def test_create_order_without_idempotency_key_skips_lookup(monkeypatch):
    client = _real_mode(monkeypatch)
    client.order.create.return_value = {"id": "order_direct"}

    order = rz.create_order(amount=200, currency="inr", receipt="rcpt", notes={})
    assert order["id"] == "order_direct"
    client.order.all.assert_not_called()


def test_fetch_order_real_mode_uses_client(monkeypatch):
    client = _real_mode(monkeypatch)
    client.order.fetch.return_value = {"id": "order_9"}
    assert rz.fetch_order("order_9") == {"id": "order_9"}
    client.order.fetch.assert_called_once_with("order_9")


# ── Real backend: payment signature ───────────────────────────────────────────


def test_verify_payment_signature_real_mode_valid(monkeypatch):
    client = _real_mode(monkeypatch)
    client.utility.verify_payment_signature.return_value = None
    assert rz.verify_payment_signature("order_1", "pay_1", "sig") is True


def test_verify_payment_signature_real_mode_invalid(monkeypatch):
    client = _real_mode(monkeypatch)
    client.utility.verify_payment_signature.side_effect = (
        razorpay.errors.SignatureVerificationError("bad")
    )
    assert rz.verify_payment_signature("order_1", "pay_1", "sig") is False


# ── Webhook signature ─────────────────────────────────────────────────────────


def test_verify_webhook_signature_false_without_secret(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    assert rz.verify_webhook_signature(b"{}", "sig") is False


def test_verify_webhook_signature_valid_and_invalid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "whsec")
    body = b'{"event": "payment.captured"}'
    good = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    assert rz.verify_webhook_signature(body, good) is True
    assert rz.verify_webhook_signature(body, "tampered") is False


# ── refund_payment ────────────────────────────────────────────────────────────


def test_fake_refund_payment_shape(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "fake")
    monkeypatch.setattr(rz, "_fake_refunds", {})

    refund = rz.refund_payment("pay_abc123", notes={"reason": "test"})

    assert refund["id"] == "rfnd_fake_pay_abc123"
    assert refund["payment_id"] == "pay_abc123"
    assert refund["status"] == "processed"
    assert rz._fake_refunds["pay_abc123"] is refund


def test_real_refund_payment_calls_client(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_BACKEND", "razorpay")
    client = MagicMock()
    client.payment.refund.return_value = {"id": "rfnd_1", "status": "processed"}
    monkeypatch.setattr(rz, "_client", client)

    refund = rz.refund_payment("pay_real", notes={"reason": "validation"})

    client.payment.refund.assert_called_once_with(
        "pay_real", {"notes": {"reason": "validation"}}
    )
    assert refund["id"] == "rfnd_1"
