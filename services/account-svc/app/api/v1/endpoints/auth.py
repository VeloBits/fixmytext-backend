"""Authentication endpoints — GET /auth/me returns the current user's profile."""

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


async def _get_subscription_tier(user_id: uuid.UUID, db: AsyncSession) -> str:
    """Return the active subscription tier for a user, defaulting to 'free'."""
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


@router.get("/me", response_model=UserResponse)
async def me(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Return the current authenticated user's profile and subscription tier."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        subscription_tier=await _get_subscription_tier(user.id, db),
        is_email_verified=user.is_email_verified,
    )
