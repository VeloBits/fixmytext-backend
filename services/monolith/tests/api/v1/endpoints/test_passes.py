"""Tests for /api/v1/passes/* endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

# ── GET /passes/catalog ──────────────────────────────────────────────────────


def test_get_catalog_default_region(anon_client, mock_db):
    """Catalog with no region param auto-detects and returns passes."""
    with patch(
        "app.services.region_service.detect_region",
        AsyncMock(return_value="US"),
    ):
        resp = anon_client.get("/api/v1/passes/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert "passes" in data
    assert "credit_packs" in data
    assert "region" in data


def test_get_catalog_explicit_region(anon_client, mock_db):
    """Catalog with explicit region=IN returns INR pricing."""
    resp = anon_client.get("/api/v1/passes/catalog?region=IN")
    assert resp.status_code == 200
    data = resp.json()
    assert data["region"] == "IN"


def test_get_catalog_invalid_region_fallback(anon_client, mock_db):
    """Invalid region falls back to default after detection."""
    with patch(
        "app.services.region_service.detect_region",
        AsyncMock(return_value="US"),
    ):
        resp = anon_client.get("/api/v1/passes/catalog?region=INVALID")
    assert resp.status_code == 200


# ── GET /passes/active ───────────────────────────────────────────────────────


def test_get_active_success(client, mock_db):
    """Authenticated user can retrieve active passes and credits."""
    call_count = 0

    async def execute_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar.return_value = 0
        return result

    mock_db.execute.side_effect = execute_side_effect

    resp = client.get("/api/v1/passes/active")
    assert resp.status_code == 200
    data = resp.json()
    assert "passes" in data
    assert "credits" in data
    assert "total_credits" in data


def test_get_active_requires_auth(unauth_client):
    """Active passes requires authentication."""
    resp = unauth_client.get("/api/v1/passes/active")
    assert resp.status_code == 401


# ── POST /passes/order ───────────────────────────────────────────────────────


def test_create_order_no_razorpay(client, mock_db):
    """When RAZORPAY_KEY_ID is empty, returns 503."""
    from app.core.config import settings

    original = settings.RAZORPAY_KEY_ID
    settings.RAZORPAY_KEY_ID = ""

    resp = client.post(
        "/api/v1/passes/order",
        json={"pass_id": "basic", "tool_ids": ["uppercase"]},
    )
    settings.RAZORPAY_KEY_ID = original
    assert resp.status_code == 503


def test_create_order_unknown_pass(client, mock_db):
    """Unknown pass_id returns 400."""
    from app.core.config import settings

    original = settings.RAZORPAY_KEY_ID
    settings.RAZORPAY_KEY_ID = "rzp_test_xxx"

    with patch(
        "app.api.v1.endpoints.passes.get_pass",
        return_value=None,
    ):
        resp = client.post(
            "/api/v1/passes/order",
            json={"pass_id": "nonexistent_pass", "tool_ids": ["uppercase"]},
        )
    settings.RAZORPAY_KEY_ID = original
    assert resp.status_code == 400


def test_create_order_requires_auth(unauth_client):
    """Creating a pass order requires authentication."""
    resp = unauth_client.post(
        "/api/v1/passes/order",
        json={"pass_id": "basic", "tool_ids": ["uppercase"]},
    )
    assert resp.status_code == 401


# ── POST /passes/credit-order ────────────────────────────────────────────────


def test_create_credit_order_no_razorpay(client, mock_db):
    """When RAZORPAY_KEY_ID is empty, returns 503."""
    from app.core.config import settings

    original = settings.RAZORPAY_KEY_ID
    settings.RAZORPAY_KEY_ID = ""

    resp = client.post(
        "/api/v1/passes/credit-order",
        json={"pack_id": "pack_10"},
    )
    settings.RAZORPAY_KEY_ID = original
    assert resp.status_code == 503


def test_create_credit_order_requires_auth(unauth_client):
    """Creating a credit order requires authentication."""
    resp = unauth_client.post(
        "/api/v1/passes/credit-order",
        json={"pack_id": "pack_10"},
    )
    assert resp.status_code == 401


# ── POST /passes/spin ────────────────────────────────────────────────────────


def test_spin_requires_auth(unauth_client):
    """Spinning the wheel requires authentication."""
    resp = unauth_client.post("/api/v1/passes/spin")
    assert resp.status_code == 401


# ── GET /passes/referral-code ────────────────────────────────────────────────


def test_referral_code_requires_auth(unauth_client):
    """Getting referral code requires authentication."""
    resp = unauth_client.get("/api/v1/passes/referral-code")
    assert resp.status_code == 401


def test_referral_code_success(client, mock_db):
    """Authenticated user gets referral code."""
    with patch(
        "app.api.v1.endpoints.passes.ensure_referral_code",
        AsyncMock(return_value="REF12345"),
    ):
        resp = client.get("/api/v1/passes/referral-code")
    assert resp.status_code == 200
    data = resp.json()
    assert data["referral_code"] == "REF12345"
    assert "referral_url" in data


# ── POST /passes/claim-referral ──────────────────────────────────────────────


def test_claim_referral_requires_auth(unauth_client):
    """Claiming a referral requires authentication."""
    resp = unauth_client.post(
        "/api/v1/passes/claim-referral",
        json={"code": "REF12345"},
    )
    assert resp.status_code == 401


def test_claim_referral_error(client, mock_db):
    """Claiming with an invalid code returns 400."""
    with patch(
        "app.api.v1.endpoints.passes.claim_referral",
        AsyncMock(return_value={"error": "Invalid referral code"}),
    ):
        resp = client.post(
            "/api/v1/passes/claim-referral",
            json={"code": "INVALID"},
        )
    assert resp.status_code == 400


def test_claim_referral_success(client, mock_db):
    """Claiming a valid referral code succeeds."""
    with patch(
        "app.api.v1.endpoints.passes.claim_referral",
        AsyncMock(return_value={"status": "success", "credits": 5}),
    ):
        resp = client.post(
            "/api/v1/passes/claim-referral",
            json={"code": "VALIDCODE"},
        )
    assert resp.status_code == 200
