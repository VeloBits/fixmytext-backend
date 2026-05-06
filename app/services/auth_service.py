"""Business logic for authentication: register, login, password reset."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.models import EmailVerificationToken, PasswordResetToken, User

logger = logging.getLogger(__name__)

# Reset tokens are short-lived by design — long-lived tokens broaden the blast
# radius of a leaked email/DB dump.
PASSWORD_RESET_TOKEN_TTL = timedelta(minutes=15)

# Verification links commonly sit in inboxes longer than reset links, so we
# allow a full day. Still short enough that a stolen DB dump from last week
# cannot be used to verify accounts today.
EMAIL_VERIFICATION_TOKEN_TTL = timedelta(hours=24)

# Resend throttle — per-user, enforced at the service layer (not the HTTP
# rate limiter) because it depends on the most-recent token's timestamp
# rather than request volume.
RESEND_VERIFICATION_COOLDOWN = timedelta(minutes=2)


def _hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest used to look up tokens in the DB."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def register(
    db: AsyncSession, email: str, password: str, display_name: str
) -> tuple[User, str]:
    """Create a new local user and issue a verification token.

    Returns the persisted user together with the raw verification token so
    the caller can log/send the verification URL. Raises 409 if the email
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

    raw_token = await _issue_email_verification_token(db, user)
    return user, raw_token


async def _issue_email_verification_token(db: AsyncSession, user: User) -> str:
    """Persist a new verification token for ``user`` and return the raw value.

    Only a SHA-256 hash is stored. The caller is responsible for delivering
    the raw token (via ``app.services.email.flows.send_verification_email``).
    """
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + EMAIL_VERIFICATION_TOKEN_TTL
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=expires_at,
        )
    )
    await db.commit()

    logger.info("EMAIL VERIFY issued user=%s", user.id)
    return raw_token


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    """Verify email + password. Raises 401 on failure."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled"
        )

    return user


async def create_password_reset_token(
    db: AsyncSession, email: str
) -> tuple[User, str] | None:
    """Issue a password reset token for the given email.

    Returns ``(user, raw_token)`` if the email matches an active user,
    otherwise ``None``. Callers must treat both outcomes identically at the
    HTTP layer to avoid leaking which emails are registered.

    Only a SHA-256 hash of the token is persisted.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(UTC) + PASSWORD_RESET_TOKEN_TTL

    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await db.commit()

    logger.info("PASSWORD RESET issued user=%s", user.id)
    return user, raw_token


async def reset_password(db: AsyncSession, raw_token: str, new_password: str) -> User:
    """Consume a reset token and set the user's new password.

    Raises 400 if the token is unknown, already used, or expired.
    """
    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    token = result.scalar_one_or_none()

    # Normalize the failure modes — a single generic error message keeps the
    # endpoint from hinting at which tokens exist.
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token",
    )
    if token is None or token.used_at is not None:
        raise invalid

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise invalid

    user = await db.get(User, token.user_id)
    if not user or not user.is_active:
        raise invalid

    user.hashed_password = hash_password(new_password)
    token.used_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)
    logger.info("PASSWORD RESET completed user=%s", user.id)
    return user


async def verify_email(db: AsyncSession, raw_token: str) -> User:
    """Consume a verification token and flip the user's ``is_email_verified``.

    Raises 400 if the token is unknown, already used, or expired. Safe to
    call on an already-verified account — the token is still consumed so it
    cannot be replayed.
    """
    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash
        )
    )
    token = result.scalar_one_or_none()

    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired verification token",
    )
    if token is None or token.used_at is not None:
        raise invalid

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise invalid

    user = await db.get(User, token.user_id)
    if not user or not user.is_active:
        raise invalid

    user.is_email_verified = True
    token.used_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)
    logger.info("EMAIL VERIFY completed user=%s", user.id)
    return user


async def resend_verification(db: AsyncSession, user: User) -> str | None:
    """Issue a fresh verification token for ``user``.

    Returns the raw token if a new one was issued, or ``None`` if the account
    is already verified (idempotent success). Raises 429 if the user tried to
    resend inside the per-user cooldown.
    """
    if user.is_email_verified:
        return None

    # Look at the most recent token to enforce the cooldown. Issued-at uses
    # created_at rather than expires_at so the window is anchored to the
    # last request, not the token lifetime.
    result = await db.execute(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id)
        .order_by(EmailVerificationToken.created_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    if latest is not None:
        created_at = latest.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if (
            created_at is not None
            and datetime.now(UTC) - created_at < RESEND_VERIFICATION_COOLDOWN
        ):
            retry_after = int(
                (
                    RESEND_VERIFICATION_COOLDOWN - (datetime.now(UTC) - created_at)
                ).total_seconds()
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Please wait {max(retry_after, 1)} seconds before "
                    "requesting another verification email."
                ),
                headers={"Retry-After": str(max(retry_after, 1))},
            )

    return await _issue_email_verification_token(db, user)
