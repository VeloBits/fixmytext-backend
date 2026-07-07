"""Extended tests for POST /auth/register.

Covers validation error paths and non-fatal email failure not in the
existing test_auth_register.py suite.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Validation: password constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_password_too_short_returns_422(async_client):
    """Password below KEYCLOAK_PASSWORD_MIN_LENGTH → 422 Unprocessable Entity."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "a@b.com", "password": "short", "display_name": "Test"},
    )
    assert response.status_code == 422
    body = response.json()
    assert any("password" in str(e).lower() for e in body.get("detail", []))


@pytest.mark.asyncio
async def test_register_password_too_long_returns_422(async_client):
    """Password over 128 characters → 422."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "a@b.com", "password": "x" * 129, "display_name": "Test"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_password_exactly_max_length_accepted(async_client):
    """Password of exactly 128 characters is accepted (no 422 from validator)."""
    with (
        patch(
            "app.api.v1.endpoints.auth_register.create_keycloak_user",
            new_callable=AsyncMock,
            return_value="00000000-0000-0000-0000-000000000001",
        ),
        patch(
            "app.api.v1.endpoints.auth_register.send_verification_email",
            new_callable=AsyncMock,
        ),
    ):
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "maxpw@example.com",
                "password": "A" * 128,
                "display_name": "MaxPW",
            },
        )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Validation: display_name constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_display_name_empty_returns_422(async_client):
    """Empty display_name → 422."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "a@b.com", "password": "ValidPass1", "display_name": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_display_name_whitespace_only_returns_422(async_client):
    """Whitespace-only display_name → 422 (validator strips then rejects empty)."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "a@b.com", "password": "ValidPass1", "display_name": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_display_name_too_long_returns_422(async_client):
    """display_name > 100 characters → 422."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "a@b.com",
            "password": "ValidPass1",
            "display_name": "N" * 101,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_display_name_stripped_of_whitespace(async_client):
    """Padded display_name is stripped; if result ≤100 chars it's accepted."""
    with (
        patch(
            "app.api.v1.endpoints.auth_register.create_keycloak_user",
            new_callable=AsyncMock,
            return_value="00000000-0000-0000-0000-000000000001",
        ),
        patch(
            "app.api.v1.endpoints.auth_register.send_verification_email",
            new_callable=AsyncMock,
        ),
    ):
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "strip@example.com",
                "password": "ValidPass1",
                "display_name": "  Alice  ",
            },
        )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Validation: invalid email
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(async_client):
    """Non-email string in the email field → 422."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "ValidPass1", "display_name": "T"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Non-fatal email send failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_verification_email_failure_still_returns_201(async_client):
    """send_verification_email raising should NOT cause register to fail (non-fatal)."""
    with (
        patch(
            "app.api.v1.endpoints.auth_register.create_keycloak_user",
            new_callable=AsyncMock,
            return_value="00000000-0000-0000-0000-000000000001",
        ),
        patch(
            "app.api.v1.endpoints.auth_register.send_verification_email",
            new_callable=AsyncMock,
            side_effect=Exception("SMTP unavailable"),
        ),
    ):
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "noemail@example.com",
                "password": "ValidPass1",
                "display_name": "NoEmail",
            },
        )
    assert response.status_code == 201
    assert "message" in response.json()


# ---------------------------------------------------------------------------
# Keycloak Admin API failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_keycloak_down_returns_502(async_client):
    """RuntimeError from create_keycloak_user (Keycloak unavailable) → 502."""
    with patch(
        "app.api.v1.endpoints.auth_register.create_keycloak_user",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Keycloak user creation failed with status 503"),
    ):
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "fail@example.com",
                "password": "ValidPass1",
                "display_name": "Fail",
            },
        )
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409_generic_message(async_client):
    """ValueError from create_keycloak_user (duplicate email) → 409 with non-leaking message."""
    with patch(
        "app.api.v1.endpoints.auth_register.create_keycloak_user",
        new_callable=AsyncMock,
        side_effect=ValueError("email exists"),
    ):
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "dup@example.com",
                "password": "ValidPass1",
                "display_name": "Dup",
            },
        )
    assert response.status_code == 409
    body = response.json()
    # Must NOT say "already registered" or leak enumeration info
    detail = body.get("detail", "")
    assert "already registered" not in detail.lower()
    assert "email" not in detail.lower() or "different" in detail.lower()
