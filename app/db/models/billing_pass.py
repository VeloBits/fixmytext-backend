"""Billing user_passes and user_pass_tools ORM models."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


class BillingUserPass(Base):
    __tablename__ = "user_passes"
    __table_args__ = (
        Index("ix_billing_user_passes_user_id", "user_id"),
        Index(
            "ix_billing_user_passes_active",
            "user_id",
            "expires_at",
            postgresql_where=text("is_active = true"),
        ),
        Index(
            "ix_user_passes_active_lookup",
            "user_id",
            "expires_at",
            postgresql_where=text("is_active = true"),
        ),
        {"schema": settings.DB_SCHEMA_BILLING},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    pass_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey(f"{settings.DB_SCHEMA_BILLING}.pass_catalog.id"),
        nullable=False,
    )
    # Denormalized at grant time so catalog changes don't affect existing passes
    tools_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    uses_per_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchased_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    uses_today: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    uses_reset_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    user: Mapped["User"] = relationship(back_populates="billing_passes")
    pass_catalog: Mapped["PassCatalog"] = relationship(back_populates="user_passes")
    tools: Mapped[list["UserPassTool"]] = relationship(
        back_populates="pass_instance", cascade="all, delete-orphan"
    )


class UserPassTool(Base):
    __tablename__ = "user_pass_tools"
    __table_args__ = (
        Index("ix_user_pass_tools_coverage", "pass_instance_id", "tool_id"),
        {"schema": settings.DB_SCHEMA_BILLING},
    )

    pass_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_BILLING}.user_passes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_id: Mapped[str] = mapped_column(String(100), primary_key=True)

    pass_instance: Mapped["BillingUserPass"] = relationship(back_populates="tools")
