"""FastAPI dependencies for the account service.

``get_current_user`` accepts EITHER a Bearer JWT (verified via Keycloak JWKS)
OR a signed session cookie (verified via the local HMAC secret). The cookie
short-circuits the JWKS round-trip on every request — once a user has
authenticated once, subsequent requests use the cookie. The Bearer path
remains the source of truth on first request and is the only acceptable auth
for token-refresh flows.

``get_optional_user`` is the same but returns ``None`` instead of raising 401
when no (or invalid) auth is provided — used by the share endpoints.
"""

import uuid

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fixmytext_shared.config.validation import is_production_like
from fixmytext_shared.security.jwt import verify_jwt_raw
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.session_cookie import verify_session
from app.db.models.user import User
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)

# In production, an empty KEYCLOAK_AUDIENCE must NOT silently disable audience
# verification — require it so a misconfiguration fails loudly instead of
# accepting any-audience tokens. Dev/test keep the lenient (skip-aud) behaviour
# so local runs without a configured audience still work. This is defence in
# depth alongside main.lifespan's assert_required_in_prod startup guard.
_REQUIRE_AUDIENCE = is_production_like(settings.ENVIRONMENT)


async def _resolve_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> uuid.UUID | None:
    """Return the authenticated user's Keycloak UUID from EITHER source.

    Tries the session cookie first (faster — no JWKS round-trip), then falls
    back to Bearer JWT. Returns ``None`` if neither yields a valid identity.
    """
    # Path A: session cookie (set by /auth/me previously)
    cookie_value = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_value and settings.SESSION_COOKIE_SECRET:
        claims = verify_session(cookie_value, settings.SESSION_COOKIE_SECRET)
        if claims and isinstance(claims.get("sub"), str):
            try:
                return uuid.UUID(claims["sub"])
            except (ValueError, KeyError):
                pass  # fall through to Bearer

    # Path B: Bearer JWT (Keycloak-issued)
    if credentials:
        try:
            payload = verify_jwt_raw(
                credentials.credentials,
                algorithm="RS256",
                jwks_url=settings.KEYCLOAK_JWKS_URL,
                audience=settings.KEYCLOAK_AUDIENCE or None,
                issuer=settings.KEYCLOAK_ISSUER or None,
                require_audience=_REQUIRE_AUDIENCE,
            )
            return uuid.UUID(payload["sub"])
        except Exception:
            return None

    return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify auth (cookie OR Bearer) and return the authenticated User ORM object.

    Performs JIT provisioning: if the Keycloak subject has no matching row
    in the DB yet, a minimal User record is created and flushed (not
    committed) so callers can extend it within the same transaction.
    """
    keycloak_id = await _resolve_user_id(request, credentials)
    if not keycloak_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await db.scalar(select(User).where(User.keycloak_id == keycloak_id))

    if user is None and credentials is not None:
        # JIT provisioning — only from Bearer (the cookie's claims are
        # echo-of-DB; the cookie is never a source of truth for new users).
        try:
            payload = verify_jwt_raw(
                credentials.credentials,
                algorithm="RS256",
                jwks_url=settings.KEYCLOAK_JWKS_URL,
                audience=settings.KEYCLOAK_AUDIENCE or None,
                issuer=settings.KEYCLOAK_ISSUER or None,
                require_audience=_REQUIRE_AUDIENCE,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=401, detail="Token expired or invalid"
            ) from exc
        email = payload.get("email", "")
        user = User(
            keycloak_id=keycloak_id,
            email=email,
            display_name=payload.get("preferred_username") or email,
            hashed_password=None,
            is_email_verified=bool(payload.get("email_verified", False)),
        )
        try:
            db.add(user)
            await db.flush()
        except IntegrityError:
            await db.rollback()
            user = await db.scalar(select(User).where(User.keycloak_id == keycloak_id))
            if user is None or user.keycloak_id != keycloak_id:
                raise HTTPException(status_code=401, detail="Not authenticated")
    elif user is None:
        # Cookie pointed at a user that doesn't exist in DB — treat as 401.
        raise HTTPException(status_code=401, detail="Not authenticated")
    elif not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Optional auth — returns User if valid cookie OR Bearer, None otherwise. Never raises."""
    keycloak_id = await _resolve_user_id(request, credentials)
    if not keycloak_id:
        return None

    user = await db.scalar(select(User).where(User.keycloak_id == keycloak_id))
    if not user or not user.is_active:
        return None
    return user
