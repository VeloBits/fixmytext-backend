"""Thin /auth/register endpoint — proxies user creation to Keycloak Admin API.

Frontend follows with a standard Authorization Code + PKCE login flow.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator

from app.core.config import settings
from app.core.rate_limit import register_limiter
from app.services.keycloak_admin import create_keycloak_user, send_verification_email

logger = logging.getLogger(__name__)
router = APIRouter()


def _client_ip(request: Request) -> str:
    """Best-effort real client IP (first X-Forwarded-For hop, else peer)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        min_len = settings.KEYCLOAK_PASSWORD_MIN_LENGTH
        if len(v) < min_len:
            raise ValueError(f"Password must be at least {min_len} characters.")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters.")
        return v

    @field_validator("display_name")
    @classmethod
    def display_name_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Display name cannot be empty.")
        if len(stripped) > 100:
            raise ValueError("Display name must be at most 100 characters.")
        return stripped


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request):
    """Create a new user in Keycloak via Admin API. Frontend follows with Authorization Code + PKCE login."""
    # Throttle per client IP before touching the Keycloak Admin API (M-8).
    await register_limiter.check(request, user_id=f"ip:{_client_ip(request)}")

    try:
        keycloak_id = await create_keycloak_user(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except ValueError:
        # Use a generic message to avoid leaking whether an email is already
        # registered (prevents user enumeration attacks).
        raise HTTPException(
            status_code=409,
            detail="Registration could not be completed. Please try a different email.",
        ) from None
    except RuntimeError as exc:
        logger.error("Keycloak user creation error: %s", exc)
        raise HTTPException(
            status_code=502, detail="Registration service unavailable."
        ) from exc

    # Trigger verification email (non-fatal if it fails)
    try:
        await send_verification_email(keycloak_id)
    except Exception as exc:  # noqa: BLE001
        # Sanitize email before logging to prevent log injection via \r\n in user input.
        safe_email = str(payload.email).replace("\r", "").replace("\n", "")
        logger.warning("Could not send verification email to %s: %s", safe_email, exc)

    return {"message": "Account created. Check your email to verify."}
