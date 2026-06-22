"""Tests for app.services.keycloak_admin.

Focuses on error paths that previously had zero coverage:
- create_keycloak_user with missing Location header (T2)
- _get_admin_token when Keycloak is unreachable (T3)
- _get_admin_token when admin credentials are wrong (401)
- create_keycloak_user with existing email (409)
- send_verification_email non-fatal failure
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_token_response(token: str = "test-admin-token", expires_in: int = 300) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": token, "expires_in": expires_in}
    return resp


def _mock_create_response(*, status: int, location: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    headers: dict[str, str] = {}
    if location is not None:
        headers["Location"] = location
    resp.headers = headers
    return resp


# ---------------------------------------------------------------------------
# T2: create_keycloak_user with missing Location header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_keycloak_user_missing_location_header():
    """Keycloak returns 201 but no Location header → RuntimeError raised.

    Silent data corruption fix: an absent Location header means we cannot
    extract the user UUID, so we raise rather than store an empty string.
    """
    from app.services.keycloak_admin import create_keycloak_user

    token_resp = _mock_token_response()
    create_resp = _mock_create_response(status=201, location=None)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    # First post → token, second post → user creation
    mock_client.post = AsyncMock(side_effect=[token_resp, create_resp])

    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Location header"):
                await create_keycloak_user(
                    email="test@example.com",
                    password="secure123",
                    display_name="Test",
                )


@pytest.mark.asyncio
async def test_create_keycloak_user_valid_location_returns_id():
    """Keycloak returns 201 with a valid Location header → returns the UUID."""
    from app.services.keycloak_admin import create_keycloak_user

    kc_id = str(uuid.uuid4())
    token_resp = _mock_token_response()
    create_resp = _mock_create_response(
        status=201,
        location=f"http://keycloak/admin/realms/Velobits-Dev/users/{kc_id}",
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=[token_resp, create_resp])

    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await create_keycloak_user(
                email="test@example.com",
                password="secure123",
                display_name="Test",
            )

    assert result == kc_id


@pytest.mark.asyncio
async def test_create_keycloak_user_duplicate_email_raises_value_error():
    """Keycloak returns 409 (conflict) → raises ValueError with a safe message."""
    from app.services.keycloak_admin import create_keycloak_user

    token_resp = _mock_token_response()
    conflict_resp = _mock_create_response(status=409)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=[token_resp, conflict_resp])

    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="already exists"):
                await create_keycloak_user(
                    email="dup@example.com",
                    password="secure123",
                    display_name="Dup",
                )


# ---------------------------------------------------------------------------
# T3: _get_admin_token when Keycloak is unreachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_admin_token_keycloak_unreachable_raises():
    """httpx.ConnectError during token fetch → RuntimeError raised with clear message.

    Wrapping the network error as RuntimeError ensures callers (create_keycloak_user
    → auth_register) always see RuntimeError and return 502, never an unhandled 500.
    """
    from app.services.keycloak_admin import _get_admin_token

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="network error"):
                await _get_admin_token()


@pytest.mark.asyncio
async def test_get_admin_token_bad_credentials_raises():
    """Keycloak returns 401 on admin-cli auth → RuntimeError with status code."""
    from app.services.keycloak_admin import _get_admin_token

    bad_resp = MagicMock()
    bad_resp.status_code = 401

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=bad_resp)

    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="401"):
                await _get_admin_token()


@pytest.mark.asyncio
async def test_get_admin_token_uses_cache():
    """Second call within TTL returns cached token without an HTTP request."""
    from app.services.keycloak_admin import _get_admin_token

    import time

    cached = {
        "token": "cached-admin-token",
        "expires_at": time.time() + 3600,
    }

    with patch("app.services.keycloak_admin._TOKEN_CACHE", cached):
        with patch("httpx.AsyncClient") as mock_cls:
            result = await _get_admin_token()

    assert result == "cached-admin-token"
    mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# H4: _get_admin_token missing access_token key in 200 response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_admin_token_missing_access_token_key_raises():
    """Keycloak returns 200 but response body lacks 'access_token' → RuntimeError.

    Guards against H4: a KeyError would propagate as an unexpected 500 instead
    of a clear auth-failure message.
    """
    from app.services.keycloak_admin import _get_admin_token

    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.json.return_value = {"token_type": "Bearer"}  # no access_token

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=bad_resp)

    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="no access_token"):
                await _get_admin_token()


# ---------------------------------------------------------------------------
# M6: create_keycloak_user UUID validation on Location header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_keycloak_user_invalid_uuid_in_location_raises():
    """Location header path segment that isn't a valid UUID → RuntimeError.

    Guards against M6: a malformed Location URL would return a garbage string
    instead of a UUID, silently corrupting keycloak_id in the application.
    """
    from app.services.keycloak_admin import create_keycloak_user

    token_resp = _mock_token_response()
    bad_location_resp = _mock_create_response(
        status=201,
        location="http://keycloak/admin/realms/Velobits-Dev/users/not-a-uuid",
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=[token_resp, bad_location_resp])

    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="invalid UUID"):
                await create_keycloak_user(
                    email="test@example.com",
                    password="secure123",
                    display_name="Test",
                )


# ---------------------------------------------------------------------------
# Network error paths — must raise RuntimeError so callers return 502, not 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_keycloak_user_network_error_raises_runtime_error():
    """httpx.ConnectError on user-creation call → RuntimeError (not raw httpx error).

    The register endpoint only catches ValueError and RuntimeError. A raw network
    error would produce an unhandled 500; wrapping it ensures a proper 502.
    """
    from app.services.keycloak_admin import create_keycloak_user

    token_resp = _mock_token_response()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    # First call returns token; second call (user creation) throws network error.
    mock_client.post = AsyncMock(
        side_effect=[token_resp, httpx.ConnectError("Connection refused")]
    )

    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="network error"):
                await create_keycloak_user(
                    email="test@example.com",
                    password="secure123",
                    display_name="Test",
                )


# ---------------------------------------------------------------------------
# send_verification_email — verify client_id + redirect_uri params are sent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_verification_email_passes_client_id_and_redirect_uri():
    """send_verification_email passes KEYCLOAK_CLIENT_ID + FRONTEND_URL as query params.

    Without these, Keycloak generates a verification link that redirects to the
    account console instead of the frontend app.
    """
    from unittest.mock import MagicMock

    from app.services.keycloak_admin import send_verification_email

    token_resp = _mock_token_response()
    verify_resp = MagicMock()
    verify_resp.status_code = 204

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.put = AsyncMock(return_value=verify_resp)

    keycloak_id = str(uuid.uuid4())
    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch(
                "app.services.keycloak_admin.settings",
                KEYCLOAK_URL="http://keycloak:8080",
                KEYCLOAK_REALM="Velobits-Dev",
                KEYCLOAK_CLIENT_ID="fixmytext-frontend",
                FRONTEND_URL="https://app.velobits.dev",
                KEYCLOAK_SERVICE_ACCOUNT_ID="",
                KEYCLOAK_SERVICE_ACCOUNT_SECRET="",
                KEYCLOAK_ADMIN="admin",
                KEYCLOAK_ADMIN_PASSWORD="pass",
            ):
                await send_verification_email(keycloak_id)

    mock_client.put.assert_awaited_once()
    call_kwargs = mock_client.put.call_args[1]
    params = call_kwargs.get("params") or {}
    assert params.get("client_id") == "fixmytext-frontend"
    assert params.get("redirect_uri") == "https://app.velobits.dev"


@pytest.mark.asyncio
async def test_send_verification_email_omits_params_when_not_configured():
    """send_verification_email sends no query params when client_id/redirect_uri unset."""
    from unittest.mock import MagicMock

    from app.services.keycloak_admin import send_verification_email

    token_resp = _mock_token_response()
    verify_resp = MagicMock()
    verify_resp.status_code = 204

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.put = AsyncMock(return_value=verify_resp)

    keycloak_id = str(uuid.uuid4())
    with patch("app.services.keycloak_admin._TOKEN_CACHE", {}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch(
                "app.services.keycloak_admin.settings",
                KEYCLOAK_URL="http://keycloak:8080",
                KEYCLOAK_REALM="Velobits-Dev",
                KEYCLOAK_CLIENT_ID="",
                FRONTEND_URL="",
                KEYCLOAK_SERVICE_ACCOUNT_ID="",
                KEYCLOAK_SERVICE_ACCOUNT_SECRET="",
                KEYCLOAK_ADMIN="admin",
                KEYCLOAK_ADMIN_PASSWORD="pass",
            ):
                await send_verification_email(keycloak_id)

    mock_client.put.assert_awaited_once()
    call_kwargs = mock_client.put.call_args[1]
    # params=None when no client_id/redirect_uri configured
    assert call_kwargs.get("params") is None
