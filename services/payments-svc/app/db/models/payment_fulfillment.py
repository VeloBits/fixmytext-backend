"""Billing payment_fulfillments ledger ORM model.

One row per Razorpay payment id (UNIQUE), inserted before any grant so that the
synchronous verify callbacks and the asynchronous webhook converge on a single
fulfillment authority. The unique index makes a replayed payment or a
verify-vs-webhook race resolve to exactly one grant. See migration 0025 and
``app/services/fulfillment_service.py``.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base


class PaymentFulfillment(Base):
    __tablename__ = "payment_fulfillments"
    __table_args__ = (
        # Idempotency guard — exactly one fulfillment per Razorpay payment id.
        Index(
            "uq_payment_fulfillments_payment_id",
            "razorpay_payment_id",
            unique=True,
        ),
        Index("ix_payment_fulfillments_user_id", "user_id"),
        {"schema": settings.DB_SCHEMA_BILLING},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    razorpay_payment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # pass | credit | pro_subscription
    item_type: Mapped[str] = mapped_column(String(30), nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount_subunits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # which path won the race: 'verify' or 'webhook'
    fulfilled_via: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    result_ref: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
