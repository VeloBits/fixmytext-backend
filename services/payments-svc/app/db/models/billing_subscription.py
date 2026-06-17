"""Billing subscription and payment_events ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_id", "user_id"),
        Index(
            "uq_subscriptions_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint("tier IN ('free', 'pro')", name="ck_subscription_tier"),
        CheckConstraint(
            "status IN ('active', 'cancelled', 'expired', 'pending')",
            name="ck_subscription_status",
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
    tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free", server_default=text("'free'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    razorpay_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_paid_subunits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    region: Mapped[str | None] = mapped_column(String(5), nullable=True)
    activated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        Index("ix_payment_events_user_id", "user_id"),
        Index(
            "ix_payment_events_payment_id",
            "razorpay_payment_id",
            postgresql_where=text("razorpay_payment_id IS NOT NULL"),
        ),
        Index(
            "ix_payment_events_razorpay_event_id",
            "razorpay_event_id",
            unique=True,
            postgresql_where=text("razorpay_event_id IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'duplicate')",
            name="ck_payment_event_status",
        ),
        {"schema": settings.DB_SCHEMA_BILLING},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    razorpay_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    item_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount_subunits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="received",
        server_default=text("'received'"),
    )
    raw_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    user: Mapped["User | None"] = relationship(back_populates="payment_events")
