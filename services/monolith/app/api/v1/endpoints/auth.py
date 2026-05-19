"""Authentication endpoints — Keycloak handles registration/login; only /me remains."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


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
