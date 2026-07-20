"""Billing user_credits ORM model."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


class BillingUserCredit(Base):
    __tablename__ = "user_credits"
    __table_args__ = (
        Index(
            "ix_billing_user_credits_active",
            "user_id",
            "created_at",
            postgresql_where=text("credits_remaining > 0"),
        ),
        Index(
            "ix_user_credits_active_lookup",
            "user_id",
            "credits_remaining",
            postgresql_where=text("credits_remaining > 0"),
        ),
        CheckConstraint(
            "credits_remaining >= 0 AND credits_remaining <= credits_total",
            name="ck_credits_remaining_valid",
        ),
        CheckConstraint(
            "source IN ('purchase', 'streak', 'quest', 'achievement', 'referral', 'welcome', 'spin')",
            name="ck_credit_source",
        ),
        Index("ix_billing_user_credits_keycloak_sub", "keycloak_sub"),
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
        index=True,
    )
    # Keycloak subject denormalized from auth.users.keycloak_id (migrations 0027/0028).
    keycloak_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    pack_id: Mapped[str | None] = mapped_column(
        String(50),
        ForeignKey(f"{settings.DB_SCHEMA_BILLING}.credit_pack_catalog.id"),
        nullable=True,
    )
    credits_total: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    credits_remaining: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    user: Mapped["User"] = relationship(back_populates="billing_credits")
    pack_catalog: Mapped["CreditPackCatalog | None"] = relationship(
        back_populates="user_credits"
    )
