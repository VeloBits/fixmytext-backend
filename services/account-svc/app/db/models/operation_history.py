"""OperationHistory ORM model — lives in the 'activity' schema."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class OperationHistory(Base):
    __tablename__ = "operation_history"
    __table_args__ = (
        Index("ix_operation_history_user_id", "user_id"),
        Index("ix_operation_history_tool_id", "tool_id"),
        Index("ix_operation_history_created_at", "created_at"),
        Index(
            "ix_op_history_user_date",
            "user_id",
            sa_text("created_at DESC"),
            postgresql_where=sa_text("is_deleted = false"),
        ),
        Index(
            "ix_op_history_user_tool_date",
            "user_id",
            "tool_id",
            sa_text("created_at DESC"),
            postgresql_where=sa_text("is_deleted = false"),
        ),
        Index(
            "ix_operation_history_user_created",
            "user_id",
            "created_at",
        ),
        {"schema": settings.DB_SCHEMA_ACTIVITY},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa_text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
    )

    # Tool identification
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_label: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # api, ai, local, select, action, drawer

    # Text snapshots (truncated to 500 chars to avoid bloating)
    input_preview: Mapped[str] = mapped_column(Text, nullable=False)
    output_preview: Mapped[str] = mapped_column(Text, nullable=False)
    input_length: Mapped[int] = mapped_column(Integer, nullable=False)
    output_length: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa_text("'success'")
    )
    # Soft delete: set is_deleted=True instead of hard deleting (migration 0012)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=sa_text("now()")
    )

    user: Mapped["User"] = relationship(back_populates="operation_history")
