"""UserToolStats ORM model — lifetime per-tool usage totals per user."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base


class UserToolStats(Base):
    __tablename__ = "user_tool_stats"
    __table_args__ = (
        Index("ix_user_tool_stats_user_uses", "user_id", text("total_uses DESC")),
        CheckConstraint("total_uses > 0", name="ck_user_tool_stats_uses_positive"),
        {"schema": settings.DB_SCHEMA_ACTIVITY},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    total_uses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    last_used_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
