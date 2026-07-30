"""SharedResult ORM model - lives in the 'activity' schema."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class SharedResult(Base):
    __tablename__ = "shared_results"
    __table_args__ = (
        Index("ix_shared_results_user_id", "user_id"),
        Index("ix_shared_results_created_at", "created_at"),
        Index("ix_shared_results_expires_at", "expires_at"),
        {"schema": settings.DB_SCHEMA_ACTIVITY},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa_text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tool_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_label: Mapped[str] = mapped_column(String(200), nullable=False)

    # Full input + output text (input_text added in migration 0013)
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_text: Mapped[str] = mapped_column(Text, nullable=False)

    # View tracking and expiry (added in migration 0013)
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=sa_text("0")
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa_text("now() + INTERVAL '30 days'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=sa_text("now()")
    )

    user: Mapped[Optional["User"]] = relationship()
