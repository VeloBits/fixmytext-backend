"""FastAPI dependencies for authentication."""

import logging
import uuid

import sentry_sdk
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from fixmytext_shared.security.jwt import verify_jwt_raw

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Strict auth dependency — raises 401 if no valid Keycloak JWT."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = verify_jwt_raw(
            credentials.credentials,
            algorithm="RS256",
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            audience=settings.KEYCLOAK_AUDIENCE or None,
        )
        keycloak_id_str: str = payload.get("sub")
        if not keycloak_id_str:
            raise HTTPException(status_code=401, detail="Invalid token")
        keycloak_id = uuid.UUID(keycloak_id_str)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Look up by keycloak_id; JIT-provision on first authenticated request
    user = await db.scalar(sa_select(User).where(User.keycloak_id == keycloak_id))
    if user is None:
        email = payload.get("email", "")
        display_name = payload.get("preferred_username") or payload.get("name") or email
        user = User(
            keycloak_id=keycloak_id,
            email=email,
            display_name=display_name,
            hashed_password=None,
            is_email_verified=bool(payload.get("email_verified", False)),
        )
        db.add(user)
        await db.flush()
        logger.info("JIT provisioned new user keycloak_id=%s email=%s", keycloak_id, email)
    elif not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

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
    """Optional auth — returns User if valid Keycloak JWT, None otherwise. Never raises 401."""
    if not credentials:
        return None
    try:
        payload = verify_jwt_raw(
            credentials.credentials,
            algorithm="RS256",
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            audience=settings.KEYCLOAK_AUDIENCE or None,
        )
        keycloak_id_str: str = payload.get("sub")
        if not keycloak_id_str:
            return None
        keycloak_id = uuid.UUID(keycloak_id_str)
    except (JWTError, ValueError):
        return None

    user = await db.scalar(sa_select(User).where(User.keycloak_id == keycloak_id))
    if not user or not user.is_active:
        return None
    return user
