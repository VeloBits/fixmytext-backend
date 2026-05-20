"""Thin /auth/register endpoint — proxies user creation to Keycloak Admin API."""
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator

from app.services.keycloak_admin import create_keycloak_user, send_verification_email

logger = logging.getLogger(__name__)
router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @field_validator("display_name")
    @classmethod
    def display_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Display name cannot be empty.")
        return v.strip()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest):
    """Create a new user in Keycloak. Frontend follows with a Direct Grant login."""
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
    except (OSError, RuntimeError) as exc:
        # Non-fatal: log without the email address to avoid PII in logs.
        logger.warning("Could not send verification email (user=%s): %s", keycloak_id, exc)

    return {"message": "Account created. Check your email to verify."}
