"""Razorpay integration service for payments."""

import hashlib
import hmac
import logging
import sys

# razorpay 1.x uses pkg_resources (removed from setuptools>=78).
# Ensure it is loadable before importing razorpay; shim with
# importlib.metadata if the real package is missing.
if "pkg_resources" not in sys.modules:
    import importlib

    try:
        importlib.import_module("pkg_resources")
    except ImportError:
        import importlib.metadata as _md
        import types

        _shim = types.ModuleType("pkg_resources")
        _shim.get_distribution = lambda name: _md.distribution(name)  # type: ignore[attr-defined]
        sys.modules["pkg_resources"] = _shim

import razorpay

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: razorpay.Client | None = None

# In-memory store for fake orders when PAYMENTS_BACKEND=fake (E2E tests).
_fake_orders: dict[str, dict] = {}


def _payments_fake() -> bool:
    return settings.PAYMENTS_BACKEND.lower() == "fake"


def payments_configured() -> bool:
    """True when payment endpoints can serve requests (real key set OR fake mode)."""
    return _payments_fake() or bool(settings.RAZORPAY_KEY_ID)


# Pro pricing per region (used by checkout endpoint)
PRO_PLAN_PRICES = {
    "IN": {"amount": 39900, "currency": "INR"},  # ₹399/mo
    "US": {"amount": 500, "currency": "USD"},  # $5/mo
    "GB": {"amount": 400, "currency": "GBP"},  # £4/mo
    "EU": {"amount": 450, "currency": "EUR"},  # €4.50/mo
}


def init_razorpay():
    """Initialize Razorpay client."""
    global _client
    if _payments_fake():
        return
    if not settings.RAZORPAY_KEY_ID:
        return
    _client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def get_client() -> razorpay.Client:
    """Return the Razorpay client instance."""
    if not _client:
        raise RuntimeError("Razorpay not initialized — set RAZORPAY_KEY_ID in .env")
    return _client


# ── Orders (one-time payments: passes, credits, Pro) ──────────────────────


def create_order(
    amount: int,
    currency: str,
    receipt: str,
    notes: dict,
    idempotency_key: str | None = None,
) -> dict:
    """Create a Razorpay order for a one-time payment.

    amount: in smallest currency unit (paise for INR, cents for USD).
    idempotency_key: if provided, checks for a recent pending order with
        the same receipt to avoid creating duplicates on retries.
    Returns order dict with 'id', 'amount', 'currency'.
    """
    if _payments_fake():
        order_id = (
            f"order_fake_{abs(hash((idempotency_key or receipt, amount, currency))):x}"
        )
        order = {
            "id": order_id,
            "amount": amount,
            "currency": currency.upper(),
            "receipt": idempotency_key or receipt,
            "notes": notes,
            "status": "created",
        }
        _fake_orders[order_id] = order
        return order

    client = get_client()

    # Check for an existing unpaid order with the same receipt to avoid
    # duplicate orders on network retries or double-clicks.
    if idempotency_key:
        try:
            existing_orders = client.order.all({"receipt": idempotency_key})
            for order in existing_orders.get("items", []):
                if (
                    order.get("status") == "created"
                    and order.get("amount") == amount
                    and order.get("currency", "").upper() == currency.upper()
                ):
                    logger.info(
                        "Returning existing order %s for receipt=%s",
                        str(order["id"]).replace("\n", "").replace("\r", ""),
                        str(idempotency_key).replace("\n", "").replace("\r", ""),
                    )
                    return order
        except Exception:
            logger.debug("Could not check existing orders, creating new one")

    return client.order.create(
        {
            "amount": amount,
            "currency": currency.upper(),
            "receipt": idempotency_key or receipt,
            "notes": notes,
        }
    )


def fetch_order(order_id: str) -> dict:
    """Fetch order details from Razorpay to validate notes."""
    if _payments_fake():
        order = _fake_orders.get(order_id)
        if not order:
            raise RuntimeError(f"Fake order {order_id} not found")
        return order
    return get_client().order.fetch(order_id)


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify Razorpay payment signature. Returns True if valid."""
    if _payments_fake():
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    try:
        get_client().utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
        return True
    except razorpay.errors.SignatureVerificationError:
        return False


# ── Webhook ──────────────────────────────────────────────────────────────


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify Razorpay webhook signature."""
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
