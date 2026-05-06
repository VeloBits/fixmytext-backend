"""Authentication endpoints: register, login, refresh, logout, me."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import (
    auth_limiter,
    forgot_password_limiter,
    verification_resend_limiter,
)
from app.core.sanitize import sanitize_log_value as _s
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    ResendVerificationResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.services.auth_service import (
    authenticate,
    create_password_reset_token,
    resend_verification,
    verify_email,
)
from app.services.auth_service import register as do_register
from app.services.auth_service import reset_password as do_reset_password
from app.services.email.flows import (
    send_password_reset_email,
    send_verification_email,
)

logger = logging.getLogger(__name__)

# Cookie configuration sourced from settings (with safe fallbacks)
REFRESH_COOKIE = getattr(settings, "COOKIE_NAME", "refresh_token")
REFRESH_COOKIE_PATH = getattr(settings, "COOKIE_PATH", "/api/v1/auth")


def _echo_tokens_in_response() -> bool:
    """Return True when raw tokens may be echoed back in API responses.

    Only true when email is going to stdout (console backend) — i.e. the dev
    workflow that grabs the token directly from the response. Once a real
    SMTP relay is configured, the token must only be retrievable from the
    inbox to exercise the real flow end-to-end.
    """
    backend = (settings.EMAIL_BACKEND or "auto").lower()
    if backend == "console":
        return True
    if backend == "smtp":
        return False
    # auto: console if no SMTP host configured
    return not settings.SMTP_HOST


router = APIRouter(prefix="/auth", tags=["Auth"])


async def _set_user_region(user, request: Request, db: AsyncSession):
    """Detect and store the user's region from their IP address.

    This is non-critical — failures are logged but do not block the request.
    The user will default to the US region if detection fails.
    """
    try:
        from app.services.region_service import resolve_user_region

        await resolve_user_region(user, request, db)
        await db.commit()
    except Exception:
        logger.warning("Failed to set user region, defaulting to US", exc_info=True)


def _set_refresh_cookie(
    response: Response, token: str, *, persistent: bool = True
) -> None:
    """Set the refresh token as an HTTP-only secure cookie on the response."""
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=getattr(settings, "COOKIE_SECURE", True),
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400 if persistent else None,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Remove the refresh token cookie from the client."""
    response.delete_cookie(key=REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


# ── Register ────────────────────────────────────


@router.post("/register", response_model=TokenResponse)
async def register(
    req: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account and return an access token pair.

    The refresh token is set as an HTTP-only cookie; only the access token
    is returned in the response body.
    """
    await auth_limiter.check(request)
    logger.info(
        "REGISTER attempt email=%s display_name=%s", _s(req.email), _s(req.display_name)
    )
    try:
        user, verification_token = await do_register(
            db, req.email, req.password, req.display_name
        )
    except HTTPException:
        logger.warning(
            "REGISTER failed email=%s (duplicate or validation error)", _s(req.email)
        )
        raise
    except Exception:
        logger.exception("REGISTER unexpected error email=%s", _s(req.email))
        raise
    # Send verification email (fire-and-forget semantics — flow swallows errors)
    await send_verification_email(user, verification_token)
    # Detect region from IP
    await _set_user_region(user, request, db)
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)
    logger.info("REGISTER success user=%s email=%s", user.id, user.email)
    return TokenResponse(access_token=access)


# ── Login ───────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email and password and return an access token.

    On success the refresh token is stored as an HTTP-only cookie. If
    ``remember_me`` is false the cookie is a session cookie (no max_age).
    """
    await auth_limiter.check(request)
    logger.info("LOGIN attempt email=%s", _s(req.email))
    user = await authenticate(db, req.email, req.password)
    # Detect region from IP if not set yet
    if not user.region:
        await _set_user_region(user, request, db)
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh, persistent=req.remember_me)
    return TokenResponse(access_token=access)


# ── Refresh ─────────────────────────────────────


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    """Exchange a valid refresh token (from cookie) for a new access/refresh pair.

    Implements token rotation: a new refresh token replaces the old one on
    every successful refresh.
    """
    await auth_limiter.check(request)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        payload = decode_token(token)
    except (JWTError, ValueError) as e:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=401, detail="Refresh token expired or invalid"
        ) from e

    if payload.get("type") != "refresh":
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = uuid.UUID(payload.get("sub"))
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Issue new token pair
    new_access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(access_token=new_access)


# ── Logout ──────────────────────────────────────


@router.post("/logout")
async def logout(response: Response, user: User = Depends(get_current_user)):
    """Log out by clearing the refresh token cookie."""
    _clear_refresh_cookie(response)
    return {"detail": "Logged out"}


# ── Forgot password ─────────────────────────────


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Issue a time-limited password reset token for the given email.

    Always returns a success response — never reveals whether the email
    is registered. Rate limited to 3 requests/minute per client IP.
    """
    await forgot_password_limiter.check(request)
    # We deliberately do not log the submitted email — it's user-controlled
    # PII, and logging it complicates compliance + invites log-injection.
    # The post-lookup branch logs the resolved user.id, which is enough to
    # trace the request without persisting raw email addresses.
    issued = await create_password_reset_token(db, req.email)
    raw_token: str | None = None
    if issued is not None:
        user, raw_token = issued
        logger.info("FORGOT_PASSWORD issued user=%s", user.id)
        await send_password_reset_email(user, raw_token)
    else:
        logger.info("FORGOT_PASSWORD ignored (unknown or inactive email)")
    # Echo the raw token only when the console backend is active (local dev,
    # no SMTP configured). Once a real relay is set up, the user retrieves
    # the token from their inbox, exercising the real flow end-to-end.
    echoed = raw_token if _echo_tokens_in_response() else None
    return ForgotPasswordResponse(reset_token=echoed)


# ── Reset password ──────────────────────────────


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Consume a password reset token and set the user's new password."""
    await auth_limiter.check(request)
    await do_reset_password(db, req.token, req.new_password)
    return ResetPasswordResponse()


# ── Verify email ────────────────────────────────


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email_endpoint(
    req: VerifyEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Consume an email verification token and mark the account verified."""
    await auth_limiter.check(request)
    logger.info("VERIFY_EMAIL attempt")
    await verify_email(db, req.token)
    return VerifyEmailResponse()


# ── Resend verification ─────────────────────────


@router.post("/resend-verification", response_model=ResendVerificationResponse)
async def resend_verification_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Issue a fresh verification email.

    Per-user cooldown (1 request / 2 minutes) is enforced via Redis-backed
    rate limiter keyed on the user's ID, so it survives across IPs/clients.
    """
    await auth_limiter.check(request)
    # Per-user cooldown lives in the rate limiter, not the service layer —
    # makes the policy uniform with other auth-flow throttles and survives
    # across machines (Redis-backed when REDIS_URL is set).
    await verification_resend_limiter.check(request, user_id=str(user.id))
    logger.info("RESEND_VERIFICATION user=%s", user.id)
    raw_token = await resend_verification(user)
    if raw_token is not None:
        await send_verification_email(user, raw_token)
    echoed = raw_token if _echo_tokens_in_response() else None
    return ResendVerificationResponse(verification_token=echoed)


# ── Me ─────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def me(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Return the current authenticated user's profile and subscription tier."""
    from app.services.pass_service import get_subscription_tier

    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        subscription_tier=await get_subscription_tier(user.id, db),
        is_email_verified=user.is_email_verified,
    )
