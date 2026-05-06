"""Direct tests for ``app.core.transactional_tokens``.

These cover the algorithmic guarantees the rest of the auth flow relies on:
* purpose-claim isolation (verify ≠ reset),
* automatic single-use semantics for password reset (pwd-version prefix),
* rejection of malformed / wrong-key / expired JWTs.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest

from app.core.transactional_tokens import (
    InvalidTransactionalToken,
    issue_email_verification_token,
    issue_password_reset_token,
    verify_email_verification_token,
    verify_password_reset_token,
)

# ── Password reset ───────────────────────────────────────────────────────────


def test_password_reset_round_trip():
    user_id = uuid.uuid4()
    hashed = "$2b$12$abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQR"
    raw = issue_password_reset_token(user_id, hashed)
    assert verify_password_reset_token(raw, hashed) == str(user_id)


def test_password_reset_rejects_after_password_change():
    """The pwd_v claim is a prefix of the bcrypt hash at issuance time. Any
    later password change → different hash → claim mismatch → reject."""
    user_id = uuid.uuid4()
    old_hash = "$2b$12$" + "A" * 53
    new_hash = "$2b$12$" + "B" * 53

    raw = issue_password_reset_token(user_id, old_hash)
    with pytest.raises(InvalidTransactionalToken):
        verify_password_reset_token(raw, new_hash)


def test_password_reset_rejects_email_verify_token():
    """An email-verify JWT must NOT be accepted as a password-reset JWT
    even though both are signed by the same secret."""
    user_id = uuid.uuid4()
    raw_verify = issue_email_verification_token(user_id)
    with pytest.raises(InvalidTransactionalToken):
        verify_password_reset_token(raw_verify, "any-hash")


def test_password_reset_rejects_garbage():
    with pytest.raises(InvalidTransactionalToken):
        verify_password_reset_token("not.a.jwt", "hash")


def test_password_reset_rejects_expired_token():
    user_id = uuid.uuid4()
    hashed = "$2b$12$" + "x" * 53
    # Mock the issuance time to make the token already expired.
    with patch("app.core.transactional_tokens.datetime") as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC) - timedelta(hours=1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        raw = issue_password_reset_token(user_id, hashed)
    with pytest.raises(InvalidTransactionalToken):
        verify_password_reset_token(raw, hashed)


def test_password_reset_rejects_wrong_signing_key():
    """A token signed by a different secret must fail signature verification."""
    user_id = uuid.uuid4()
    hashed = "$2b$12$" + "y" * 53

    forged = jwt.encode(
        {
            "sub": str(user_id),
            "purpose": "pwd-reset",
            "pwd_v": hashed[:20],
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        },
        "wrong-secret-key",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTransactionalToken):
        verify_password_reset_token(forged, hashed)


# ── Email verification ───────────────────────────────────────────────────────


def test_email_verify_round_trip():
    user_id = uuid.uuid4()
    raw = issue_email_verification_token(user_id)
    assert verify_email_verification_token(raw) == str(user_id)


def test_email_verify_rejects_password_reset_token():
    user_id = uuid.uuid4()
    hashed = "$2b$12$" + "z" * 53
    raw_reset = issue_password_reset_token(user_id, hashed)
    with pytest.raises(InvalidTransactionalToken):
        verify_email_verification_token(raw_reset)


def test_email_verify_rejects_garbage():
    with pytest.raises(InvalidTransactionalToken):
        verify_email_verification_token("not.a.jwt")
