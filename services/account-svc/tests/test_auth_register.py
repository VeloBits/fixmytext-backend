"""Endpoint tests for POST /api/v1/auth/register (+ the M-8 per-IP rate limit).

Keycloak Admin API calls are mocked, so no Keycloak is needed. Each test uses a
distinct X-Forwarded-For IP so the module-level register limiter buckets don't
bleed across tests.
"""

import uuid
from unittest.mock import AsyncMock, patch

from app.core.config import settings

REGISTER = "/api/v1/auth/register"
VALID = {
    "email": "new@example.com",
    "password": "longenough1",
    "display_name": "New User",
}


def _hdr(ip: str) -> dict:
    return {"x-forwarded-for": ip}


async def test_register_success_returns_201(async_client):
    with (
        patch(
            "app.api.v1.endpoints.auth_register.create_keycloak_user",
            new=AsyncMock(return_value=str(uuid.uuid4())),
        ),
        patch(
            "app.api.v1.endpoints.auth_register.send_verification_email",
            new=AsyncMock(return_value=None),
        ),
    ):
        resp = await async_client.post(
            REGISTER, json=VALID, headers=_hdr("198.51.100.10")
        )
    assert resp.status_code == 201
    assert "message" in resp.json()


async def test_register_duplicate_email_returns_409(async_client):
    with patch(
        "app.api.v1.endpoints.auth_register.create_keycloak_user",
        new=AsyncMock(side_effect=ValueError("already exists")),
    ):
        resp = await async_client.post(
            REGISTER,
            json={**VALID, "email": "dup@example.com"},
            headers=_hdr("198.51.100.11"),
        )
    assert resp.status_code == 409  # generic message — no user enumeration


async def test_register_service_error_returns_502(async_client):
    with patch(
        "app.api.v1.endpoints.auth_register.create_keycloak_user",
        new=AsyncMock(side_effect=RuntimeError("keycloak down")),
    ):
        resp = await async_client.post(
            REGISTER,
            json={**VALID, "email": "err@example.com"},
            headers=_hdr("198.51.100.12"),
        )
    assert resp.status_code == 502


async def test_register_short_password_returns_422(async_client):
    resp = await async_client.post(
        REGISTER, json={**VALID, "password": "short"}, headers=_hdr("198.51.100.13")
    )
    assert resp.status_code == 422


async def test_register_rate_limited_after_cap(async_client):
    """M-8: the (cap+1)-th registration from one IP is throttled with 429."""
    ip = "198.51.100.99"
    cap = settings.REGISTER_RATE_LIMIT_MAX_REQUESTS
    with (
        patch(
            "app.api.v1.endpoints.auth_register.create_keycloak_user",
            new=AsyncMock(return_value=str(uuid.uuid4())),
        ),
        patch(
            "app.api.v1.endpoints.auth_register.send_verification_email",
            new=AsyncMock(return_value=None),
        ),
    ):
        for i in range(cap):
            ok = await async_client.post(
                REGISTER, json={**VALID, "email": f"u{i}@example.com"}, headers=_hdr(ip)
            )
            assert ok.status_code == 201
        over = await async_client.post(
            REGISTER, json={**VALID, "email": "over@example.com"}, headers=_hdr(ip)
        )
    assert over.status_code == 429
