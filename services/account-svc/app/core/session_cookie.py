"""Session cookie sign/verify for the FixMyText product app cookie.

Cookie format: ``<base64url(json_payload)>.<hex(hmac_sha256(payload, secret))>``

The cookie is HttpOnly, host-only (no Domain attribute), and signed with a
server-side secret. It carries the user's identity claims after a successful
OIDC token exchange and stays valid until ``exp``.

This is the **per-app session cookie** (FIXMYTEXT_SESSION) — distinct from
Keycloak's SSO cookie which is scoped to ``.velobits.dev``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import TypedDict


class SessionClaims(TypedDict, total=False):
    sub: str
    email: str
    email_verified: bool
    roles: list[str]
    exp: int
    iat: int


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def sign_session(claims: SessionClaims, secret: str) -> str:
    """Serialize and HMAC-SHA256 sign the session claims.

    Returns a string of the form ``<payload>.<sig>`` suitable for use as a
    cookie value.
    """
    payload_json = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    payload_b64 = _b64url_encode(payload_json)
    sig = hmac.new(
        secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session(token: str, secret: str) -> SessionClaims | None:
    """Verify the signature and expiry of a session cookie token.

    Returns the decoded claims dict on success, ``None`` on any failure
    (malformed, bad signature, expired). Uses constant-time signature
    comparison to prevent timing attacks.
    """
    if not token or "." not in token:
        return None

    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError:
        return None

    expected_sig = hmac.new(
        secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        payload_json = _b64url_decode(payload_b64)
        claims: SessionClaims = json.loads(payload_json)
    except (ValueError, json.JSONDecodeError):
        return None

    # Required fields
    if not isinstance(claims.get("sub"), str) or not isinstance(
        claims.get("email"), str
    ):
        return None

    # Expiry check
    exp = claims.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None

    return claims


def build_claims(
    *,
    sub: str,
    email: str,
    email_verified: bool,
    roles: list[str],
    max_age_seconds: int,
) -> SessionClaims:
    """Build a SessionClaims dict with computed ``iat`` and ``exp``."""
    now = int(time.time())
    return {
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "roles": roles,
        "iat": now,
        "exp": now + max_age_seconds,
    }
