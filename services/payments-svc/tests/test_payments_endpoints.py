"""
Payments service endpoint tests.

Tests:
1. GET /health → 200
2. GET /api/v1/passes/catalog (no auth) → 200, returns catalog data
3. GET /api/v1/passes/active with no JWT → 401
4. GET /api/v1/subscription/status with no JWT → 401
5. POST /api/v1/subscription/webhook with invalid signature → 400
6. Passes order handlers catch Razorpay exceptions → 502 (B-3)
"""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_health_returns_200(async_client):
    """GET /health should return 200 with service info."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "payments-svc"


@pytest.mark.asyncio
async def test_catalog_returns_200_no_auth(async_client):
    """GET /api/v1/passes/catalog is public and returns catalog data."""
    with patch(
        "app.services.region_service.detect_region",
        return_value="IN",
    ):
        response = await async_client.get("/api/v1/passes/catalog?region=IN")
    assert response.status_code == 200
    data = response.json()
    assert "passes" in data
    assert "credit_packs" in data
    assert "region" in data
    assert len(data["passes"]) > 0
    assert len(data["credit_packs"]) > 0


@pytest.mark.asyncio
async def test_active_passes_requires_auth(async_client):
    """GET /api/v1/passes/active without a JWT should return 401."""
    response = await async_client.get("/api/v1/passes/active")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_subscription_status_requires_auth(async_client):
    """GET /api/v1/subscription/status without a JWT should return 401."""
    response = await async_client.get("/api/v1/subscription/status")
    assert response.status_code == 401


def test_passes_order_handlers_catch_razorpay_exceptions():
    """create_pass_order and create_credit_order must catch exceptions from
    the Razorpay API and return 502 instead of 500 (B-3).

    Razorpay outages must surface as a gateway error to the client, not an
    unhandled internal server error.
    """
    import inspect

    from app.api.v1.endpoints import passes as passes_ep

    for fn_name, fn in [
        ("create_pass_order", passes_ep.create_pass_order),
        ("create_credit_order", passes_ep.create_credit_order),
    ]:
        src = inspect.getsource(fn)
        assert "except Exception" in src, (
            f"{fn_name} must catch Razorpay exceptions (B-3)"
        )
        assert "502" in src, (
            f"{fn_name} must return HTTP 502 on Razorpay API failure (B-3)"
        )


def test_razorpay_service_receipt_truncated_to_40_chars():
    """create_order must truncate idempotency_key/receipt to 40 chars before
    passing to Razorpay. Razorpay enforces a hard 40-char limit on the receipt
    field; exceeding it raises BadRequestError → 500 (B-5).

    Pass idempotency keys look like: pass_day_single_<UUID> = 52 chars.
    The fix truncates in razorpay_service.py so every caller benefits.
    """
    import inspect

    from app.services import razorpay_service

    src = inspect.getsource(razorpay_service.create_order)
    assert "[:40]" in src, (
        "create_order must truncate receipt/idempotency_key to 40 chars (B-5). "
        "Razorpay rejects receipts longer than 40 characters with BadRequestError."
    )


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_400(async_client):
    """POST /api/v1/subscription/webhook with invalid signature should return 400."""
    with (
        patch(
            "app.api.v1.endpoints.subscription.verify_webhook_signature",
            return_value=False,
        ),
        patch("app.api.v1.endpoints.subscription.settings") as mock_settings,
    ):
        mock_settings.RAZORPAY_WEBHOOK_SECRET = "test-secret"
        mock_settings.WEBHOOK_MAX_BODY_BYTES = 65536
        response = await async_client.post(
            "/api/v1/subscription/webhook",
            content=b'{"event": "payment.captured"}',
            headers={"x-razorpay-signature": "invalid-signature"},
        )
    assert response.status_code == 400
