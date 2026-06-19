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

import logging
import uuid

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fixmytext_shared.auth.jit import jit_provision_user
from fixmytext_shared.config.validation import is_production_like
from fixmytext_shared.security.jwt import verify_jwt_raw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.session_cookie import verify_session
from app.db.models.user import User
from app.db.session import get_db

logger = logging.getLogger(__name__)

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
) -> tuple[uuid.UUID | None, dict | None]:
    """Return (keycloak_id, jwt_payload) from EITHER cookie OR Bearer.

    Cookie path: returns (uuid, None) — no raw JWT payload; faster (no JWKS).
    Bearer path: returns (uuid, payload) — payload already verified once.
    Neither/invalid: returns (None, None).

    Returning the payload avoids a second ``verify_jwt_raw`` call in
    ``get_current_user`` when JIT provisioning is needed.
    """
    # Path A: session cookie (set by /auth/me previously)
    cookie_value = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_value and settings.SESSION_COOKIE_SECRET:
        claims = verify_session(cookie_value, settings.SESSION_COOKIE_SECRET)
        if claims and isinstance(claims.get("sub"), str):
            try:
                logger.debug("auth: resolved via session cookie")
                return uuid.UUID(claims["sub"]), None
            except ValueError:
                logger.warning("auth: session cookie sub is not a valid UUID — ignoring cookie")
                pass  # fall through to Bearer

    # Path B: Bearer JWT (Keycloak-issued)
    if credentials:
        try:
            payload = await verify_jwt_raw(
                credentials.credentials,
                algorithm="RS256",
                jwks_url=settings.KEYCLOAK_JWKS_URL,
                audience=settings.KEYCLOAK_AUDIENCE or None,
                issuer=settings.KEYCLOAK_ISSUER or None,
                require_audience=_REQUIRE_AUDIENCE,
            )
            logger.debug("auth: resolved via Bearer JWT")
            return uuid.UUID(payload["sub"]), payload
        except httpx.HTTPError as exc:
            logger.warning("auth: JWKS fetch failed — treating as 401: %s", exc)
            return None, None
        except Exception as exc:
            logger.debug("auth: Bearer JWT invalid: %s", exc)
            return None, None

    return None, None


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
    keycloak_id, jwt_payload = await _resolve_user_id(request, credentials)
    if not keycloak_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await db.scalar(select(User).where(User.keycloak_id == keycloak_id))

    if user is None and jwt_payload is not None:
        # JIT provisioning — only when the Bearer was verified (jwt_payload
        # present). Cookie-only auth means the session cookie is stale (user
        # deleted from DB); that case falls through to 401 below.
        user = await jit_provision_user(db, User, keycloak_id, jwt_payload)
    elif user is None:
        # Cookie pointed at a user that doesn't exist in DB — treat as 401.
        raise HTTPException(status_code=401, detail="Not authenticated")
    elif not user.is_active:
        logger.info("auth: inactive user keycloak_id=%s rejected", keycloak_id)
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Optional auth — returns User if valid cookie OR Bearer, None otherwise. Never raises."""
    keycloak_id, _ = await _resolve_user_id(request, credentials)
    if not keycloak_id:
        return None

    user = await db.scalar(select(User).where(User.keycloak_id == keycloak_id))
    if not user or not user.is_active:
        return None
    return user
