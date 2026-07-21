"""UserTemplate ORM model — lives in the 'activity' schema."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


class UserTemplate(Base):
    __tablename__ = "user_templates"
    __table_args__ = (
        Index(
            "ix_user_templates_user_active",
            "user_id",
            sa_text("created_at DESC"),
            postgresql_where=sa_text("is_deleted = false"),
        ),
        Index("ix_activity_user_templates_keycloak_sub", "keycloak_sub"),
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
        index=True,
    )
    # Keycloak subject denormalized from auth.users.keycloak_id (migrations 0027/0028).
    keycloak_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Soft delete added in migration 0014
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=sa_text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=sa_text("now()"), onupdate=datetime.now
    )

    user: Mapped["User"] = relationship(back_populates="templates")
