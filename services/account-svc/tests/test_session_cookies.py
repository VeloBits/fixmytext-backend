"""Tests for the per-app session cookie.

Covers:
1. sign_session → verify_session round-trip
2. Tampered signature returns None
3. Expired claims return None
4. Missing required fields return None
5. Malformed input returns None
6. POST /auth/session/clear returns 204 with Max-Age=0 cookie
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from starlette.responses import Response

from app.core.session_cookie import build_claims, sign_session, verify_session

SECRET = "test-secret-at-least-32-characters-long"


def _claims(**overrides):
    base = build_claims(
        sub="11111111-1111-1111-1111-111111111111",
        email="user@example.com",
        email_verified=True,
        roles=["user"],
        max_age_seconds=3600,
    )
    base.update(overrides)
    return base


def test_sign_then_verify_returns_original_claims():
    claims = _claims()
    token = sign_session(claims, SECRET)
    decoded = verify_session(token, SECRET)
    assert decoded is not None
    assert decoded["sub"] == claims["sub"]
    assert decoded["email"] == claims["email"]
    assert decoded["email_verified"] is True
    assert decoded["roles"] == ["user"]


def test_tampered_signature_returns_none():
    claims = _claims()
    token = sign_session(claims, SECRET)
    payload_b64, sig = token.split(".", 1)
    # Flip the last hex char of the signature.
    flipped = "0" if sig[-1] != "0" else "1"
    tampered = f"{payload_b64}.{sig[:-1]}{flipped}"
    assert verify_session(tampered, SECRET) is None


def test_tampered_payload_returns_none():
    claims = _claims()
    token = sign_session(claims, SECRET)
    payload_b64, sig = token.split(".", 1)
    # Replace one char of the payload; signature will no longer match.
    tampered = f"{payload_b64[:-1]}X.{sig}"
    assert verify_session(tampered, SECRET) is None


def test_wrong_secret_returns_none():
    claims = _claims()
    token = sign_session(claims, SECRET)
    assert verify_session(token, "different-secret") is None


def test_expired_token_returns_none():
    # Use 10 seconds in the past — well beyond the 5-second leeway added by B2 fix.
    claims = _claims(exp=int(time.time()) - 10)
    token = sign_session(claims, SECRET)
    assert verify_session(token, SECRET) is None


def test_missing_sub_returns_none():
    claims = _claims()
    del claims["sub"]
    token = sign_session(claims, SECRET)
    assert verify_session(token, SECRET) is None


def test_missing_email_returns_none():
    claims = _claims()
    del claims["email"]
    token = sign_session(claims, SECRET)
    assert verify_session(token, SECRET) is None


def test_malformed_token_returns_none():
    assert verify_session("", SECRET) is None
    assert verify_session("not-a-cookie", SECRET) is None
    assert verify_session("nodot", SECRET) is None
    assert verify_session("!!!!.!!!!", SECRET) is None


def test_session_cookie_subject_is_keycloak_id(monkeypatch):
    """M-7: the cookie `sub` is the Keycloak id (what get_current_user matches
    on), not the DB primary key — otherwise the cookie never resolves a user."""
    from app.api.v1.endpoints import auth as auth_mod

    monkeypatch.setattr(auth_mod.settings, "SESSION_COOKIE_SECRET", SECRET)
    db_id = "11111111-1111-1111-1111-111111111111"
    kc_id = "22222222-2222-2222-2222-222222222222"
    user = SimpleNamespace(
        id=db_id, keycloak_id=kc_id, email="u@e.com", is_email_verified=True
    )

    response = Response()
    auth_mod._set_session_cookie(response, user)

    set_cookie = response.headers.get("set-cookie", "")
    assert "fixmytext_session=" in set_cookie
    value = set_cookie.split("fixmytext_session=", 1)[1].split(";", 1)[0]
    claims = verify_session(value, SECRET)
    assert claims is not None
    assert claims["sub"] == kc_id
    assert claims["sub"] != db_id


def test_session_cookie_skipped_without_keycloak_id(monkeypatch):
    """A user with no keycloak_id gets no cookie (rather than a bad one)."""
    from app.api.v1.endpoints import auth as auth_mod

    monkeypatch.setattr(auth_mod.settings, "SESSION_COOKIE_SECRET", SECRET)
    user = SimpleNamespace(
        id="x", keycloak_id=None, email="u@e.com", is_email_verified=True
    )
    response = Response()
    auth_mod._set_session_cookie(response, user)
    assert "set-cookie" not in {k.lower() for k in response.headers}


def test_email_field_wrong_type_returns_none():
    """T7: verify_session returns None when the email field is not a string.

    session_cookie.py requires both sub and email to be strings. A cookie with
    email=123 passes JSON decoding but fails the type check.
    """
    claims = _claims()
    claims["email"] = 123  # integer, not a string
    token = sign_session(claims, SECRET)
    assert verify_session(token, SECRET) is None


def test_build_claims_exp_minus_iat_equals_max_age():
    """T8: exp - iat == max_age_seconds within a 2-second tolerance."""
    max_age = 7200
    claims = build_claims(
        sub="11111111-1111-1111-1111-111111111111",
        email="user@example.com",
        email_verified=True,
        roles=["user"],
        max_age_seconds=max_age,
    )
    delta = claims["exp"] - claims["iat"]
    assert abs(delta - max_age) <= 2


@pytest.mark.asyncio
async def test_set_session_cookie_no_secret_no_cookie(async_client):
    """T6: GET /auth/me with valid Bearer but empty SESSION_COOKIE_SECRET → 200,
    no Set-Cookie header."""
    import uuid
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    fake_user = MagicMock()
    fake_user.id = uuid.uuid4()
    fake_user.keycloak_id = kc_id
    fake_user.email = "user@example.com"
    fake_user.display_name = "Test"
    fake_user.is_active = True
    fake_user.is_email_verified = True

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=fake_user)
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def override_get_db():
        yield mock_db

    _MOCK_TARGET = "app.core.deps.verify_jwt_raw"
    payload = {"sub": str(kc_id), "email": "user@example.com", "email_verified": True}

    with patch(_MOCK_TARGET, return_value=payload):
        with patch("app.api.v1.endpoints.auth.settings") as mock_settings:
            mock_settings.SESSION_COOKIE_SECRET = ""
            mock_settings.SESSION_COOKIE_NAME = "fixmytext_session"
            mock_settings.SESSION_COOKIE_MAX_AGE = 3600
            mock_settings.SESSION_COOKIE_SECURE = False
            mock_settings.SESSION_COOKIE_DOMAIN = ""
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = await async_client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": "Bearer valid.jwt.token"},
                )
                assert response.status_code == 200
                assert "fixmytext_session" not in response.headers.get("set-cookie", "")
            finally:
                app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_clear_session_endpoint_returns_204_with_expired_cookie(async_client):
    """POST /api/v1/auth/session/clear → 204 + Set-Cookie with Max-Age=0."""
    response = await async_client.post("/api/v1/auth/session/clear")
    assert response.status_code == 204
    set_cookie = response.headers.get("set-cookie", "")
    assert "fixmytext_session=" in set_cookie.lower()
    # Cookie deletion is signaled by Max-Age=0 (or expires in the past)
    assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()
