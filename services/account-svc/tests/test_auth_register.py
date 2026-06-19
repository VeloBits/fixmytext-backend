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


async def test_register_verification_email_failure_still_returns_201(async_client):
    """T5: If send_verification_email raises, POST /auth/register still returns 201.

    The exception is swallowed (lines 69-74 of auth_register.py). The user account
    was already created in Keycloak; a failed verification email is non-fatal.
    """
    with (
        patch(
            "app.api.v1.endpoints.auth_register.create_keycloak_user",
            new=AsyncMock(return_value=str(uuid.uuid4())),
        ),
        patch(
            "app.api.v1.endpoints.auth_register.send_verification_email",
            new=AsyncMock(side_effect=RuntimeError("SMTP down")),
        ),
    ):
        resp = await async_client.post(
            REGISTER,
            json={**VALID, "email": "smtp-fail@example.com"},
            headers=_hdr("198.51.100.20"),
        )
    assert resp.status_code == 201


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


async def test_register_password_min_length_enforced_via_config(async_client):
    """KEYCLOAK_PASSWORD_MIN_LENGTH is honoured: an 8-char password must fail
    when the config is raised to 12 (matching the production Keycloak realm)."""
    from app.api.v1.endpoints import auth_register

    original = settings.KEYCLOAK_PASSWORD_MIN_LENGTH
    settings.KEYCLOAK_PASSWORD_MIN_LENGTH = 12
    try:
        resp = await async_client.post(
            REGISTER,
            json={**VALID, "password": "Abcdefg1", "email": "minlen@example.com"},
            headers=_hdr("198.51.100.50"),
        )
        assert resp.status_code == 422
        detail = str(resp.json())
        assert "12" in detail
    finally:
        settings.KEYCLOAK_PASSWORD_MIN_LENGTH = original


async def test_register_password_at_configured_min_length_accepted(async_client):
    """A password of exactly KEYCLOAK_PASSWORD_MIN_LENGTH chars passes validation."""
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
        min_len = settings.KEYCLOAK_PASSWORD_MIN_LENGTH
        exact_password = "A" * min_len
        resp = await async_client.post(
            REGISTER,
            json={**VALID, "password": exact_password, "email": "exact@example.com"},
            headers=_hdr("198.51.100.51"),
        )
    assert resp.status_code == 201


async def test_register_password_one_below_min_length_rejected(async_client):
    """A password one char below KEYCLOAK_PASSWORD_MIN_LENGTH is rejected with 422."""
    min_len = settings.KEYCLOAK_PASSWORD_MIN_LENGTH
    short_password = "A" * (min_len - 1)
    resp = await async_client.post(
        REGISTER,
        json={**VALID, "password": short_password, "email": "short@example.com"},
        headers=_hdr("198.51.100.52"),
    )
    assert resp.status_code == 422
