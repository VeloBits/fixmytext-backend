"""Tests for ``app.core.token_hash``.

The module hashes server-generated random tokens (reset / verify links). It
must NOT be used for user passwords — those live in ``app.core.security``
and use bcrypt. These tests verify the algorithmic properties we rely on.
"""

import secrets
from unittest.mock import patch

from app.core.token_hash import hash_token


def test_hash_is_deterministic():
    """Same input must produce the same digest — required for DB lookups."""
    raw = secrets.token_urlsafe(32)
    assert hash_token(raw) == hash_token(raw)


def test_hash_differs_for_different_tokens():
    a = hash_token(secrets.token_urlsafe(32))
    b = hash_token(secrets.token_urlsafe(32))
    assert a != b


def test_hash_is_64_hex_chars():
    """HMAC-SHA256 hex output is always 64 characters."""
    h = hash_token("anything")
    assert len(h) == 64
    int(h, 16)  # raises if not valid hex


def test_hash_does_not_leak_raw_token():
    """The digest must not contain the raw token (sanity)."""
    raw = "supersecret-raw-value-1234567890"
    h = hash_token(raw)
    assert raw not in h


def test_hash_changes_when_secret_key_changes():
    """The HMAC key is settings.SECRET_KEY — flipping it must yield a
    different digest. This is the property that defends against offline
    lookup attacks on a leaked DB."""
    raw = "shared-input"
    with patch("app.core.token_hash.settings") as s:
        s.SECRET_KEY = "first-secret"
        h1 = hash_token(raw)
        s.SECRET_KEY = "second-secret"
        h2 = hash_token(raw)
    assert h1 != h2
