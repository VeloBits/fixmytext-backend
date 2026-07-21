"""UserPreferences ORM model — lives in the 'auth' schema."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    __table_args__ = {"schema": settings.DB_SCHEMA_AUTH}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    theme: Mapped[str] = mapped_column(
        String(10), default="dark", server_default=text("'dark'")
    )
    # Transitional: personas were replaced by custom tool groups (2026-07-14).
    # The column is read-only legacy state — migration 0004 consumed it to seed
    # starter groups + onboarding_seen; PreferencesUpdate no longer accepts it.
    # Drop the column (and the PreferencesResponse field) in a later migration
    # once no deployed bundle reads it.
    persona: Mapped[str | None] = mapped_column(String(50), nullable=True)
    theme_skin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.now
    )

    user: Mapped["User"] = relationship(back_populates="preferences")
