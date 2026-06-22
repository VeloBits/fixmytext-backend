"""Authentication endpoints.

- ``GET  /auth/me``                  — return current user profile + issue session cookie
- ``POST /auth/session/clear``       — clear the per-app session cookie on logout
- ``POST /auth/backchannel-logout``  — Keycloak SLO hook: revoke sessions server-side
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from fixmytext_shared.security.jwt import verify_jwt_raw

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.redis import is_session_revoked, revoke_session
from app.core.session_cookie import build_claims, sign_session, verify_session
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

_COOKIE_DOMAIN = settings.SESSION_COOKIE_DOMAIN or None


async def _get_subscription_tier(user_id: uuid.UUID, db: AsyncSession) -> str:
    """Return the active subscription tier for a user, defaulting to 'free'."""
    try:
        row = await db.execute(
            text(
                "SELECT tier FROM billing.subscriptions"
                " WHERE user_id = :uid AND status = 'active'"
                " LIMIT 1"
            ),
            {"uid": str(user_id)},
        )
        result = row.scalar_one_or_none()
        return result if result is not None else "free"
    except Exception:
        logger.warning("Failed to fetch subscription tier for user %s — defaulting to free", user_id)
        return "free"


def _set_session_cookie(
    response: Response, user: User, roles: list[str] | None = None
) -> None:
    """Sign and set the per-app session cookie on the response.

    No-op if SESSION_COOKIE_SECRET is unset (treated as a misconfiguration in
    non-dev environments — handled by config validation).
    """
    if not settings.SESSION_COOKIE_SECRET:
        return
    # The cookie `sub` MUST be the Keycloak id: get_current_user resolves the
    # cookie via `User.keycloak_id == sub` (M-7). Signing the DB primary key
    # here made the cookie never resolve (silent Bearer fallback). Skip the
    # cookie for any user lacking a keycloak_id (should not occur post-cutover).
    if not user.keycloak_id:
        return
    claims = build_claims(
        sub=str(user.keycloak_id),
        email=user.email,
        email_verified=user.is_email_verified,
        roles=roles or [],
        max_age_seconds=settings.SESSION_COOKIE_MAX_AGE,
    )
    token = sign_session(claims, settings.SESSION_COOKIE_SECRET)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
        domain=_COOKIE_DOMAIN,
        path="/",
    )


@router.get("/me", response_model=UserResponse)
async def me(
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current authenticated user's profile and subscription tier.

    Side effect: issues the ``fixmytext_session`` cookie. The browser stores it
    HttpOnly + host-only, and from this request onward the cookie is sufficient
    for authentication on subsequent requests (Bearer JWT is still accepted in
    parallel for the transition window — see ``get_current_user``).
    """
    response.headers["Cache-Control"] = "no-store"
    _set_session_cookie(response, user)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        subscription_tier=await _get_subscription_tier(user.id, db),
        is_email_verified=user.is_email_verified,
    )


@router.post("/session/clear", status_code=204)
async def clear_session(request: Request, response: Response) -> Response:
    """Clear the per-app session cookie. Called by the frontend on logout
    BEFORE redirecting to Keycloak's end-session endpoint.

    No auth required — clearing is idempotent. As a side effect the current
    session is added to the Redis revocation set so it cannot be replayed
    even if the browser ignores the Max-Age=0 instruction.
    """
    # Add the current session to the Redis revocation set before deleting it
    # client-side. This closes the window where a stolen cookie could be used
    # after logout even if the browser fails to delete it.
    cookie_value = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_value and settings.SESSION_COOKIE_SECRET:
        claims = verify_session(cookie_value, settings.SESSION_COOKIE_SECRET)
        if claims and isinstance(claims.get("sub"), str):
            await revoke_session(claims["sub"], settings.SESSION_COOKIE_MAX_AGE)

    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        domain=_COOKIE_DOMAIN,
        path="/",
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
    )
    response.status_code = 204
    return response


@router.post("/backchannel-logout", status_code=200, include_in_schema=False)
async def backchannel_logout(
    logout_token: Annotated[str, Form()],
) -> dict:
    """Keycloak backchannel Single Log-Out hook.

    Keycloak calls this endpoint server-to-server (application/x-www-form-urlencoded)
    when a session ends via OIDC SLO. Verifies the signed logout token and marks
    all sessions for the identified user as revoked in Redis.

    Returns 200 on success or 400 on an invalid/unrecognised token. Keycloak
    retries on 5xx; never returns 5xx for a missing Redis (fail-open to avoid
    blocking Keycloak's logout flow when Redis is temporarily unavailable).
    """
    if not settings.KEYCLOAK_JWKS_URL:
        logger.warning("backchannel-logout: KEYCLOAK_JWKS_URL not configured — rejecting")
        raise HTTPException(status_code=400, detail="IdP not configured")

    try:
        # Logout tokens carry `aud = client_id` per OIDC Back-Channel Logout spec
        # (section 2.4), not the resource-server audience stored in KEYCLOAK_AUDIENCE.
        # Verify signature + issuer only; the event claim below is the discriminator
        # that confirms this is actually a logout token.
        payload = await verify_jwt_raw(
            logout_token,
            algorithm="RS256",
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            audience=None,
            issuer=settings.KEYCLOAK_ISSUER or None,
            require_audience=False,
        )
    except Exception as exc:
        logger.warning("backchannel-logout: invalid logout token: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid logout token")

    # Spec (OIDC CIBA): logout token MUST contain the backchannel-logout event.
    events = payload.get("events", {})
    if "http://schemas.openid.net/event/backchannel-logout" not in events:
        logger.warning("backchannel-logout: missing backchannel-logout event claim")
        raise HTTPException(status_code=400, detail="Not a backchannel logout token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=400, detail="Missing sub claim")

    await revoke_session(sub, settings.SESSION_COOKIE_MAX_AGE)
    logger.info("backchannel-logout: sessions revoked for sub=%s", sub)
    return {}
