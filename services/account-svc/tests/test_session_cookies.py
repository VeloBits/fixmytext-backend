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
    claims = _claims(exp=int(time.time()) - 1)
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


@pytest.mark.asyncio
async def test_clear_session_endpoint_returns_204_with_expired_cookie(async_client):
    """POST /api/v1/auth/session/clear → 204 + Set-Cookie with Max-Age=0."""
    response = await async_client.post("/api/v1/auth/session/clear")
    assert response.status_code == 204
    set_cookie = response.headers.get("set-cookie", "")
    assert "fixmytext_session=" in set_cookie.lower()
    # Cookie deletion is signaled by Max-Age=0 (or expires in the past)
    assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()
