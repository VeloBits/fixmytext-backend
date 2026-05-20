"""Pydantic schemas for authentication requests and responses."""

from pydantic import BaseModel


class UserResponse(BaseModel):
    """Response containing the authenticated user's profile."""

    id: str
    email: str
    display_name: str
    subscription_tier: str = "free"
    is_email_verified: bool = False
