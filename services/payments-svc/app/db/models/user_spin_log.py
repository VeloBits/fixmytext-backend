"""UserSpinLog ORM model - one spin per ISO week per user (enforced by composite PK)."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base


class UserSpinLog(Base):
    __tablename__ = "user_spin_log"
    __table_args__ = (
        Index("ix_user_spin_log_user_id", "user_id"),
        {"schema": settings.DB_SCHEMA_AUTH},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # ISO year + week as composite PK enforces one spin per week per user at DB level
    iso_year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    iso_week: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    spin_date: Mapped[date] = mapped_column(Date, nullable=False)
    reward_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reward_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
