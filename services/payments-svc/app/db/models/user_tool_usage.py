"""UserToolUsage ORM model - per-user per-tool per-day usage counter."""

import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base


class UserToolUsage(Base):
    __tablename__ = "user_tool_usage"
    __table_args__ = (
        Index(
            "ix_user_tool_usage_user_date",
            "user_id",
            "usage_date",
            postgresql_include=["tool_id", "use_count"],
        ),
        CheckConstraint("use_count > 0", name="ck_user_tool_use_count_positive"),
        {"schema": settings.DB_SCHEMA_AUTH},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    usage_date: Mapped[date] = mapped_column(
        Date, primary_key=True, server_default=text("CURRENT_DATE")
    )
    use_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default=text("1")
    )
