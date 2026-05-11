"""Business logic for authentication: register, login, password reset,
email verification.

Transactional tokens (password reset, email verify) are stateless JWTs
issued and verified by :mod:`app.core.transactional_tokens`. There is no
DB table for them — the JWT signature provides integrity, the ``exp`` claim
provides expiry, and per-flow custom claims provide single-use semantics.
See that module's docstring for the rationale.
"""

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.core.transactional_tokens import (
    InvalidTransactionalToken,
    issue_email_verification_token,
    issue_password_reset_token,
    verify_email_verification_token,
    verify_password_reset_token,
)
from app.db.models import User

logger = logging.getLogger(__name__)


async def register(
    db: AsyncSession, email: str, password: str, display_name: str
) -> tuple[User, str]:
    """Create a new local user and issue a verification token.

    Returns the persisted user together with the raw verification JWT so
    the caller can deliver the verification URL. Raises 409 if the email
    is already taken.
    """
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(
        email=email,
        hashed_password=hash_password(password),
        display_name=display_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    raw_token = issue_email_verification_token(user.id)
    logger.info("EMAIL VERIFY issued user=%s", user.id)
    return user, raw_token


# A precomputed bcrypt hash used only to equalize timing when the supplied
# email doesn't exist. The plaintext is irrelevant — what matters is that we
# spend roughly the same amount of CPU on bcrypt regardless of whether the
# user was found, so response time can't be used to enumerate accounts.
_DUMMY_BCRYPT_HASH = "$2b$12$3FSFccd5LXuscFZeRQFy.epo9pQqbhEpWEE2m90DjmP0mB7fdGIpG"


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    """Verify email + password. Raises 401 with a generic message on any failure.

    Missing user, wrong password, and disabled account are all collapsed into
    the same response to avoid leaking which case applies. When the user is
    missing we still run a bcrypt verify against a dummy hash so the response
    time doesn't reveal that the email is unregistered.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
    )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        # Equalize timing: do the bcrypt work we would have done.
        verify_password(password, _DUMMY_BCRYPT_HASH)
        raise invalid

    if not verify_password(password, user.hashed_password):
        raise invalid

    if not user.is_active:
        raise invalid

    return user


# ── Password reset ───────────────────────────────────────────────────────────


async def create_password_reset_token(
    db: AsyncSession, email: str
) -> tuple[User, str] | None:
    """Issue a password reset JWT for the given email.

    Returns ``(user, raw_jwt)`` if the email matches an active user,
    otherwise ``None``. Callers must treat both outcomes identically at the
    HTTP layer to avoid leaking which emails are registered.

    The JWT carries a prefix of the user's current bcrypt hash, so it is
    automatically invalidated by any subsequent password change.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None

    raw_jwt = issue_password_reset_token(user.id, user.hashed_password)
    logger.info("PASSWORD RESET issued user=%s", user.id)
    return user, raw_jwt


async def reset_password(db: AsyncSession, raw_jwt: str, new_password: str) -> User:
    """Consume a reset JWT and set the user's new password.

    Raises 400 if the token is unknown, malformed, expired, or no longer
    matches the user's current password version (i.e. the password was
    already changed since the token was issued).
    """
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token",
    )

    # Loading the user up-front lets us validate the JWT's pwd_v claim
    # against the current bcrypt hash without a second round-trip.
    user_id_str: str
    try:
        # We must know which user to fetch before we can check pwd_v, so we
        # do an "unsafe" decode first to extract sub. The full validation
        # (signature, expiry, purpose, pwd_v) happens immediately after.
        from jwt import decode as _jwt_decode_unverified

        unverified = _jwt_decode_unverified(
            raw_jwt, options={"verify_signature": False}
        )
        user_id_str = unverified.get("sub", "")
    except Exception as exc:
        raise invalid from exc

    if not user_id_str:
        raise invalid
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise invalid from exc

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise invalid

    try:
        verify_password_reset_token(raw_jwt, user.hashed_password)
    except InvalidTransactionalToken as exc:
        raise invalid from exc

    user.hashed_password = hash_password(new_password)
    await db.commit()
    await db.refresh(user)
    logger.info("PASSWORD RESET completed user=%s", user.id)
    return user


# ── Email verification ───────────────────────────────────────────────────────


async def verify_email(db: AsyncSession, raw_jwt: str) -> User:
    """Consume a verification JWT and flip the user's ``is_email_verified``.

    Raises 400 if the token is unknown, malformed, or expired. Idempotent:
    calling it on an already-verified user just leaves the flag set.
    """
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired verification token",
    )
    try:
        user_id_str = verify_email_verification_token(raw_jwt)
    except InvalidTransactionalToken as exc:
        raise invalid from exc

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise invalid from exc

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise invalid

    user.is_email_verified = True
    await db.commit()
    await db.refresh(user)
    logger.info("EMAIL VERIFY completed user=%s", user.id)
    return user


async def resend_verification(user: User) -> str | None:
    """Issue a fresh verification JWT for ``user``.

    Returns the raw token if a new one was issued, or ``None`` if the
    account is already verified (idempotent success). Per-user cooldown
    enforcement happens at the endpoint layer via ``verification_resend_limiter``.
    """
    if user.is_email_verified:
        return None
    raw_jwt = issue_email_verification_token(user.id)
    logger.info("EMAIL VERIFY re-issued user=%s", user.id)
    return raw_jwt
