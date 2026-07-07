"""Share endpoints -- create and view shareable links for transformed text.

Supports anonymous creation (no auth required) with configurable expiry and
text-length limits driven by ``settings.SHARE_EXPIRE_DAYS`` and
``settings.MAX_SHARE_TEXT_LENGTH``.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_optional_user
from app.db.models import User
from app.db.models.shared_result import SharedResult
from app.db.session import get_db
from app.schemas.share import ShareCreate, SharedResultView, ShareResponse

router = APIRouter(prefix="/share", tags=["Share"])

# Pull tunables from centralised settings so operators can adjust via env vars
# without a code change.  Falls back to sensible defaults if the attribute is
# not yet defined on the Settings class.
SHARE_EXPIRE_DAYS: int = getattr(settings, "SHARE_EXPIRE_DAYS", 30)
MAX_SHARE_TEXT_LENGTH: int = getattr(settings, "MAX_SHARE_TEXT_LENGTH", 50_000)


@router.post("", response_model=ShareResponse)
async def create_share(
    req: ShareCreate,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a shareable link for a transformed result.

    Authentication is optional -- anonymous visitors may also create shares.
    The output text is truncated to ``MAX_SHARE_TEXT_LENGTH`` characters.
    """
    row = SharedResult(
        user_id=user.id if user else None,
        tool_id=req.tool_id,
        tool_label=req.tool_label,
        output_text=req.output_text[:MAX_SHARE_TEXT_LENGTH],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    share_url = f"{settings.FRONTEND_URL}/share/{row.id}"
    return ShareResponse(id=str(row.id), share_url=share_url)


@router.get("/{share_id}", response_model=SharedResultView)
async def get_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
):
    """View a shared result by its public ID.

    No authentication required.  Returns 410 Gone if the share has passed
    the ``SHARE_EXPIRE_DAYS`` window.
    """
    try:
        sid = uuid.UUID(share_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Share not found") from e

    result = await db.execute(select(SharedResult).where(SharedResult.id == sid))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Share not found")

    if row.created_at < datetime.now(UTC) - timedelta(days=SHARE_EXPIRE_DAYS):
        raise HTTPException(status_code=410, detail="This share has expired")

    return SharedResultView(
        id=str(row.id),
        tool_id=row.tool_id,
        tool_label=row.tool_label,
        output_text=row.output_text,
        created_at=row.created_at.isoformat(),
    )
