"""User ORM model — lives in the 'auth' schema."""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email", "email", unique=True),
        Index("uq_users_referral_code", "referral_code", unique=True),
        Index("ix_auth_users_email", "email"),
        {"schema": settings.DB_SCHEMA_AUTH},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    keycloak_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True), nullable=True, unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # ── Referral ───────────────────────────────────────────────────────────────
    referral_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    referred_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    region: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    # Billing-schema entities
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payment_events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    billing_passes: Mapped[list["BillingUserPass"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    billing_credits: Mapped[list["BillingUserCredit"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
