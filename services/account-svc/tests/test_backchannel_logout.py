"""Tests for POST /api/v1/auth/backchannel-logout.

Keycloak calls this endpoint server-to-server (application/x-www-form-urlencoded)
with a signed logout_token JWT when a session ends via OIDC SLO.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_VERIFY = "app.api.v1.endpoints.auth.verify_jwt_raw"
_REVOKE = "app.api.v1.endpoints.auth.revoke_session"
_SETTINGS = "app.api.v1.endpoints.auth.settings"

_JWKS_URL = "http://keycloak:8080/realms/Velobits-Dev/protocol/openid-connect/certs"

_VALID_PAYLOAD = {
    "sub": "user-keycloak-uuid-1234",
    "iss": "http://keycloak:8080/realms/Velobits-Dev",
    "aud": "fixmytext-backend",
    "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
}


def _mock_settings(**overrides):
    """Return a MagicMock settings object with KEYCLOAK_JWKS_URL set."""
    m = MagicMock()
    m.KEYCLOAK_JWKS_URL = _JWKS_URL
    m.KEYCLOAK_AUDIENCE = "fixmytext-backend"
    m.KEYCLOAK_ISSUER = ""
    m.SESSION_COOKIE_NAME = "fixmytext_session"
    m.SESSION_COOKIE_SECRET = "test-secret-at-least-32-chars-long"
    m.SESSION_COOKIE_MAX_AGE = 604800
    m.SESSION_COOKIE_SECURE = False
    m.SESSION_COOKIE_DOMAIN = ""
    m.BACKCHANNEL_SECRET = ""  # default: no shared-secret guard
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


async def _post_logout(async_client, logout_token: str = "signed.logout.token"):
    return await async_client.post(
        "/api/v1/auth/backchannel-logout",
        data={"logout_token": logout_token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_logout_token_returns_200(async_client):
    """A correctly signed logout token with the backchannel-logout event revokes
    the session and returns 200 {}."""
    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(return_value=_VALID_PAYLOAD)),
        patch(_REVOKE, new=AsyncMock()) as mock_revoke,
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 200
    assert resp.json() == {}
    mock_revoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_valid_logout_token_revokes_correct_sub(async_client):
    """revoke_session is called with the sub from the logout token."""
    payload = {**_VALID_PAYLOAD, "sub": "specific-user-sub-abc"}
    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(return_value=payload)),
        patch(_REVOKE, new=AsyncMock()) as mock_revoke,
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 200
    args = mock_revoke.call_args[0]
    assert args[0] == "specific-user-sub-abc"
    assert args[1] == 604800


# ---------------------------------------------------------------------------
# Invalid token — JWT verification failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_token_signature_returns_400(async_client):
    """A JWT with a bad signature is rejected with 400."""
    import jwt

    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(side_effect=jwt.InvalidSignatureError("bad sig"))),
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 400
    assert "Invalid logout token" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_expired_token_returns_400(async_client):
    """An expired logout token is rejected with 400."""
    import jwt

    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(side_effect=jwt.ExpiredSignatureError("expired"))),
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_malformed_token_string_returns_400(async_client):
    """A completely malformed string is rejected with 400."""
    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(side_effect=ValueError("malformed"))),
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Missing or wrong event claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_events_claim_returns_400(async_client):
    """A logout token without the events claim is rejected with 400."""
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "events"}
    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(return_value=payload)),
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 400
    assert "backchannel" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_wrong_event_type_returns_400(async_client):
    """A token with a different event type (not backchannel-logout) is rejected."""
    payload = {
        **_VALID_PAYLOAD,
        "events": {"http://schemas.openid.net/event/some-other-event": {}},
    }
    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(return_value=payload)),
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Missing sub claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_sub_claim_returns_400(async_client):
    """A logout token without a sub claim is rejected with 400."""
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "sub"}
    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(return_value=payload)),
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 400
    assert "sub" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# JWKS URL not configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_jwks_url_returns_400(async_client):
    """If KEYCLOAK_JWKS_URL is not configured the endpoint returns 400 immediately."""
    with patch(_SETTINGS, new=_mock_settings(KEYCLOAK_JWKS_URL="")):
        resp = await _post_logout(async_client)

    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Redis unavailable — fail-open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_unavailable_still_returns_200(async_client):
    """If Redis is down, revoke_session is a no-op but the endpoint returns 200.

    Keycloak retries on 5xx; returning 200 prevents an infinite retry loop
    when Redis is temporarily unavailable.
    """
    with (
        patch(_SETTINGS, new=_mock_settings()),
        patch(_VERIFY, new=AsyncMock(return_value=_VALID_PAYLOAD)),
        patch(_REVOKE, new=AsyncMock(return_value=None)),
    ):
        resp = await _post_logout(async_client)

    assert resp.status_code == 200
