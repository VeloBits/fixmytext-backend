"""Tests for app.services.keycloak_admin.

Covers the two surviving helpers after the /auth/register proxy removal
(auth is Keycloak-hosted only):
- _get_admin_token: network failure, bad credentials, caching, missing token key
- send_verification_email: client_id/redirect_uri param handling
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_token_response(
    token: str = "test-admin-token", expires_in: int = 300
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": token, "expires_in": expires_in}
    return resp


# ---------------------------------------------------------------------------
# _get_admin_token when Keycloak is unreachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_admin_token_keycloak_unreachable_raises():
    """httpx.ConnectError during token fetch → RuntimeError with a clear message.

    Wrapping the network error as RuntimeError ensures callers
    (send_verification_email) see a predictable error rather than a raw httpx
    exception surfacing as an unhandled 500.
    """
    from app.services.keycloak_admin import _get_admin_token

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with (
        patch("app.services.keycloak_admin._TOKEN_CACHE", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="network error"),
    ):
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

    with (
        patch("app.services.keycloak_admin._TOKEN_CACHE", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="401"),
    ):
        await _get_admin_token()


@pytest.mark.asyncio
async def test_get_admin_token_uses_cache():
    """Second call within TTL returns cached token without an HTTP request."""
    import time

    from app.services.keycloak_admin import _get_admin_token

    cached = {
        "token": "cached-admin-token",
        "expires_at": time.time() + 3600,
    }

    with (
        patch("app.services.keycloak_admin._TOKEN_CACHE", cached),
        patch("httpx.AsyncClient") as mock_cls,
    ):
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

    with (
        patch("app.services.keycloak_admin._TOKEN_CACHE", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(RuntimeError, match="no access_token"),
    ):
        await _get_admin_token()


# ---------------------------------------------------------------------------
# send_verification_email — verify client_id + redirect_uri params are sent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_verification_email_passes_client_id_and_redirect_uri():
    """send_verification_email passes KEYCLOAK_CLIENT_ID + FRONTEND_URL as query params.

    Without these, Keycloak generates a verification link that redirects to the
    account console instead of the frontend app.
    """
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
    with (
        patch("app.services.keycloak_admin._TOKEN_CACHE", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
        patch(
            "app.services.keycloak_admin.settings",
            KEYCLOAK_URL="http://keycloak:8080",
            KEYCLOAK_REALM="Velobits-Dev",
            KEYCLOAK_CLIENT_ID="fixmytext-frontend",
            FRONTEND_URL="https://app.velobits.dev",
            KEYCLOAK_SERVICE_ACCOUNT_ID="",
            KEYCLOAK_SERVICE_ACCOUNT_SECRET="",
            KEYCLOAK_ADMIN="admin",
            KEYCLOAK_ADMIN_PASSWORD="pass",
        ),
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
    with (
        patch("app.services.keycloak_admin._TOKEN_CACHE", {}),
        patch("httpx.AsyncClient", return_value=mock_client),
        patch(
            "app.services.keycloak_admin.settings",
            KEYCLOAK_URL="http://keycloak:8080",
            KEYCLOAK_REALM="Velobits-Dev",
            KEYCLOAK_CLIENT_ID="",
            FRONTEND_URL="",
            KEYCLOAK_SERVICE_ACCOUNT_ID="",
            KEYCLOAK_SERVICE_ACCOUNT_SECRET="",
            KEYCLOAK_ADMIN="admin",
            KEYCLOAK_ADMIN_PASSWORD="pass",
        ),
    ):
        await send_verification_email(keycloak_id)

    mock_client.put.assert_awaited_once()
    call_kwargs = mock_client.put.call_args[1]
    # params=None when no client_id/redirect_uri configured
    assert call_kwargs.get("params") is None
