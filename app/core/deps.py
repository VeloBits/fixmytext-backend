"""FastAPI dependencies for authentication."""

import logging
import uuid

import sentry_sdk
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Strict auth dependency — raises 401 if no valid token."""
    if not credentials:
        logger.debug("AUTH   no credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            logger.warning("AUTH   invalid token type: %s", payload.get("type"))
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id_str: str = payload.get("sub")
        if not user_id_str:
            logger.warning("AUTH   token missing 'sub' claim")
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError) as exc:
        logger.warning("AUTH   token decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        logger.warning("AUTH   user not found or inactive: %s", user_id)
        raise HTTPException(status_code=401, detail="User not found or inactive")
    logger.debug("AUTH   authenticated user=%s", user_id)
    sentry_sdk.set_user({"id": str(user.id)})
    return user


async def get_verified_user(
    user: User = Depends(get_current_user),
) -> User:
    """Strict auth + email-verification gate.

    Use on endpoints that should be reachable only by fully-onboarded users
    (AI tools, write endpoints that assume a trustworthy identity). Returns a
    403 with a machine-readable ``code`` so the frontend can prompt the user
    to verify without treating it as a generic auth failure.
    """
    if not user.is_email_verified:
        logger.info("AUTH   user=%s blocked: email not verified", user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "email_not_verified",
                "message": (
                    "Please verify your email address to use AI-powered tools."
                ),
            },
        )
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Optional auth — returns User if valid token, None otherwise. Never raises 401."""
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            return None
        user_id_str: str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        return None

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        return None
    return user
