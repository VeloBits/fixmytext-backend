"""UserDailyLogin ORM model — append-only daily login record per user."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base


class UserDailyLogin(Base):
    __tablename__ = "user_daily_logins"
    __table_args__ = (
        Index("ix_user_daily_logins_user_id", "user_id"),
        {"schema": settings.DB_SCHEMA_AUTH},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    login_date: Mapped[date] = mapped_column(
        Date, primary_key=True, server_default=text("CURRENT_DATE")
    )
