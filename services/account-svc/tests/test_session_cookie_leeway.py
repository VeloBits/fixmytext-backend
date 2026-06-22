"""Tests for the 5-second clock-skew leeway added to verify_session (B2 fix).

Prior to the fix, a cookie with exp == now was rejected (exp < now). After
the fix, cookies within _LEEWAY=5 seconds of expiry are still accepted.
"""

from __future__ import annotations

import time

import pytest

from app.core.session_cookie import build_claims, sign_session, verify_session

SECRET = "test-secret-at-least-32-characters-long"


def _expired_by(seconds: int) -> dict:
    """Return claims that expired `seconds` ago (positive = past, negative = future)."""
    now = int(time.time())
    return {
        "sub": "11111111-1111-1111-1111-111111111111",
        "email": "user@example.com",
        "email_verified": True,
        "roles": [],
        "iat": now - 3600,
        "exp": now - seconds,
    }


def test_cookie_expired_within_leeway_is_accepted():
    """Cookie expired 3 seconds ago is still valid (within 5-second leeway)."""
    claims = _expired_by(3)
    token = sign_session(claims, SECRET)
    result = verify_session(token, SECRET)
    assert result is not None


def test_cookie_expired_exactly_at_leeway_boundary_is_accepted():
    """Cookie expired exactly 4 seconds ago is still valid (leeway is 5s)."""
    claims = _expired_by(4)
    token = sign_session(claims, SECRET)
    result = verify_session(token, SECRET)
    assert result is not None


def test_cookie_expired_beyond_leeway_is_rejected():
    """Cookie expired 10 seconds ago is rejected (beyond 5-second leeway)."""
    claims = _expired_by(10)
    token = sign_session(claims, SECRET)
    result = verify_session(token, SECRET)
    assert result is None


def test_cookie_not_yet_expired_is_accepted():
    """Cookie with future exp is always accepted."""
    claims = build_claims(
        sub="11111111-1111-1111-1111-111111111111",
        email="user@example.com",
        email_verified=True,
        roles=[],
        max_age_seconds=3600,
    )
    token = sign_session(claims, SECRET)
    assert verify_session(token, SECRET) is not None


def test_cookie_expired_long_ago_is_still_rejected():
    """Cookie expired an hour ago remains rejected regardless of leeway."""
    claims = _expired_by(3600)
    token = sign_session(claims, SECRET)
    assert verify_session(token, SECRET) is None
