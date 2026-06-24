"""UserGamification ORM model — lives in the 'activity' schema."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class UserGamification(Base):
    __tablename__ = "user_gamification"
    __table_args__ = (
        Index(
            "ix_gamification_achievements_gin",
            "achievements",
            postgresql_using="gin",
        ),
        Index(
            "ix_gamification_completed_quests_gin",
            "completed_quests",
            postgresql_using="gin",
        ),
        Index("ix_activity_user_gamification_keycloak_sub", "keycloak_sub"),
        {"schema": settings.DB_SCHEMA_ACTIVITY},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Keycloak subject denormalized from auth.users.keycloak_id (migrations 0027/0028).
    keycloak_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    streak_current: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )

    streak_last_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_quest_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    total_ops: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    total_chars: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0")
    )

    # ── JSONB kept: bounded append-only sets, only need membership checks via GIN ──
    achievements: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    completed_quests: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )

    daily_quest_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    daily_quest_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.now
    )

    user: Mapped["User"] = relationship(back_populates="gamification")
