"""Pydantic schemas for authentication requests and responses."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Request schema for user registration."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ..., min_length=8, max_length=128, description="Password (8-128 chars)"
    )
    display_name: str = Field(
        ..., min_length=1, max_length=100, description="Display name"
    )


class LoginRequest(BaseModel):
    """Request schema for user login."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    remember_me: bool = Field(
        False, description="Persist session across browser restarts"
    )


class TokenResponse(BaseModel):
    """Response containing a JWT access token."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105


class UserResponse(BaseModel):
    """Response containing the authenticated user's profile."""

    id: str
    email: str
    display_name: str
    subscription_tier: str = "free"
    is_email_verified: bool = False


class VerifyEmailRequest(BaseModel):
    """Request schema for verifying an email via a one-time token."""

    token: str = Field(
        ..., min_length=1, description="Token from the verification email"
    )


class VerifyEmailResponse(BaseModel):
    """Confirmation that the email was verified successfully."""

    detail: str = "Email verified successfully."


class ResendVerificationResponse(BaseModel):
    """Opaque response for /auth/resend-verification.

    ``verification_token`` is echoed back **only** when the console email
    backend is active (dev convenience — grab it from the response instead
    of an inbox). It is ``None`` whenever a real SMTP relay is configured,
    so production responses never leak the raw token.
    """

    detail: str = "If your email is unverified, a new verification link has been sent."
    verification_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    """Request schema for initiating a password reset."""

    email: EmailStr = Field(..., description="Email address to send a reset link to")


class ForgotPasswordResponse(BaseModel):
    """Opaque response — identical shape whether or not the email exists.

    ``reset_token`` is echoed back **only** when the console email backend
    is active (dev convenience). It is ``None`` whenever a real SMTP relay
    is configured, so production responses never leak the raw token.
    """

    detail: str = "If that email is registered, a reset link has been sent."
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    """Request schema for completing a password reset."""

    token: str = Field(
        ..., min_length=1, description="Token issued by /forgot-password"
    )
    new_password: str = Field(
        ..., min_length=8, max_length=128, description="New password (8-128 chars)"
    )


class ResetPasswordResponse(BaseModel):
    """Confirmation that the password was reset successfully."""

    detail: str = "Password has been reset."
