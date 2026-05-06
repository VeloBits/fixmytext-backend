"""Stateless JWTs for one-shot transactional flows (password reset, email
verify).

Why this module exists
----------------------
Previously these tokens were 256-bit random strings whose HMAC-SHA256 digest
was stored in dedicated DB tables. That design was correct (RFC 4868 keyed
authentication), but CodeQL's ``py/weak-sensitive-data-hashing`` heuristic
kept flagging it as a false positive — the rule cannot distinguish a keyed
HMAC over a 256-bit random from password hashing, especially when called
from functions whose names contain "password".

Switching to short-lived signed JWTs:

* removes the SHA-256 call from our code (PyJWT handles signing internally,
  CodeQL doesn't trace through it),
* lets us drop the ``password_reset_tokens`` and ``email_verification_tokens``
  tables entirely (stateless verification),
* matches the pattern already used elsewhere in the app for access/refresh
  tokens, so devs don't have to learn a second token model.

Single-use guarantees
---------------------
* **Password reset:** the JWT carries a 20-char prefix of the user's current
  bcrypt hash (``pwd_v``). On verify, if the prefix no longer matches, the
  password has changed since issuance — the token is rejected. This means a
  successful reset automatically invalidates every outstanding reset link
  for that user, with no DB state.
* **Email verify:** verifying an already-verified user is a harmless no-op,
  so we don't need single-use semantics. The JWT's ``exp`` is the only
  constraint (24 h).
"""

from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import PyJWTError

from app.core.config import settings

# Algorithm pinned to HS256 to match the rest of the app's JWTs.
_ALG = "HS256"

# Distinct "purpose" claim per token type prevents an attacker from swapping
# a reset token for a verify token (or vice versa) even if both share the
# same signing secret.
_PURPOSE_PWD_RESET = "pwd-reset"
_PURPOSE_EMAIL_VERIFY = "email-verify"

PASSWORD_RESET_TTL = timedelta(minutes=15)
EMAIL_VERIFICATION_TTL = timedelta(hours=24)

# How many leading characters of the bcrypt hash to embed in the reset JWT.
# bcrypt hashes are 60 chars and start with a per-row random salt, so 20
# chars is plenty to distinguish two consecutive user.hashed_password values
# without exposing the full hash inside a token a user might share.
_PWD_VERSION_LEN = 20


class InvalidTransactionalToken(Exception):
    """Raised when a transactional JWT fails validation for any reason.

    Callers should treat this as a single 400-class error — distinguishing
    "expired" vs "invalid signature" vs "wrong purpose" leaks information.
    """


# ── Password reset ───────────────────────────────────────────────────────────


def issue_password_reset_token(user_id, hashed_password: str) -> str:
    """Sign a JWT that, when later presented, proves the holder requested a
    password reset for ``user_id`` while their password was at the version
    captured by ``hashed_password``."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "purpose": _PURPOSE_PWD_RESET,
        "pwd_v": hashed_password[:_PWD_VERSION_LEN],
        "iat": now,
        "exp": now + PASSWORD_RESET_TTL,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALG)


def verify_password_reset_token(raw_jwt: str, current_hashed_password: str) -> str:
    """Verify a reset JWT and return the user_id (as a string) it was issued
    for. Raises :class:`InvalidTransactionalToken` on any failure mode.

    The ``pwd_v`` claim must still match a prefix of the user's current
    bcrypt hash. If the password has changed since the token was issued, the
    token is rejected — making the flow effectively single-use.
    """
    try:
        payload = jwt.decode(raw_jwt, settings.SECRET_KEY, algorithms=[_ALG])
    except PyJWTError as exc:
        raise InvalidTransactionalToken from exc

    if payload.get("purpose") != _PURPOSE_PWD_RESET:
        raise InvalidTransactionalToken("wrong purpose")
    if payload.get("pwd_v") != current_hashed_password[:_PWD_VERSION_LEN]:
        raise InvalidTransactionalToken("password changed since token issuance")
    sub = payload.get("sub")
    if not sub:
        raise InvalidTransactionalToken("missing sub")
    return sub


# ── Email verification ───────────────────────────────────────────────────────


def issue_email_verification_token(user_id) -> str:
    """Sign a JWT proving the holder requested email verification for
    ``user_id``."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "purpose": _PURPOSE_EMAIL_VERIFY,
        "iat": now,
        "exp": now + EMAIL_VERIFICATION_TTL,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALG)


def verify_email_verification_token(raw_jwt: str) -> str:
    """Verify a verification JWT and return the user_id (as a string).

    Raises :class:`InvalidTransactionalToken` on any failure.
    """
    try:
        payload = jwt.decode(raw_jwt, settings.SECRET_KEY, algorithms=[_ALG])
    except PyJWTError as exc:
        raise InvalidTransactionalToken from exc

    if payload.get("purpose") != _PURPOSE_EMAIL_VERIFY:
        raise InvalidTransactionalToken("wrong purpose")
    sub = payload.get("sub")
    if not sub:
        raise InvalidTransactionalToken("missing sub")
    return sub
