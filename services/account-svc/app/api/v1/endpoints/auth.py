"""Authentication endpoints.

- ``GET  /auth/me``           — return current user profile + issue session cookie
- ``POST /auth/session/clear`` — clear the per-app session cookie on logout
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.session_cookie import build_claims, sign_session
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


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
        samesite="lax",
        domain=settings.SESSION_COOKIE_DOMAIN if settings.SESSION_COOKIE_DOMAIN else None,
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
    _set_session_cookie(response, user)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        subscription_tier=await _get_subscription_tier(user.id, db),
        is_email_verified=user.is_email_verified,
    )


@router.post("/session/clear", status_code=204)
async def clear_session(response: Response) -> Response:
    """Clear the per-app session cookie. Called by the frontend on logout
    BEFORE redirecting to Keycloak's end-session endpoint.

    No auth required — clearing is idempotent and a hostile actor can't do
    anything by spamming this endpoint other than logging themselves out.
    """
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        domain=settings.SESSION_COOKIE_DOMAIN if settings.SESSION_COOKIE_DOMAIN else None,
        path="/",
    )
    response.status_code = 204
    return response
