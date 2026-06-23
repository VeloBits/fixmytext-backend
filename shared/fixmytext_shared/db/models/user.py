"""Shared User ORM factory.

Creates a SQLAlchemy User ORM class bound to a specific declarative Base and
auth schema string. Both account-svc and payments-svc call this factory with
their own Base and schema so each service gets a properly registered model
without duplicating the column definitions.

Usage::

    from fixmytext_shared.db.models.user import make_user_class
    from app.db.session import Base
    from app.core.config import settings

    User = make_user_class(Base, settings.DB_SCHEMA_AUTH)
"""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def make_user_class(base: type[DeclarativeBase], auth_schema: str) -> type:
    """Return a User ORM class registered with *base* under *auth_schema*.

    Service-specific relationships (e.g. subscriptions, payment_events) are
    intentionally omitted — each service adds them after calling this factory
    if needed:

        User = make_user_class(Base, settings.DB_SCHEMA_AUTH)
        User.subscriptions = relationship("Subscription", back_populates="user", ...)
    """

    class User(base):  # type: ignore[valid-type]
        __tablename__ = "users"
        __table_args__: Any = (
            Index("uq_users_email", "email", unique=True),
            Index("uq_users_referral_code", "referral_code", unique=True),
            Index("ix_auth_users_email", "email"),
            {"schema": auth_schema},
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
            sa.UUID(as_uuid=True), nullable=True, index=True
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
            TIMESTAMP(timezone=True),
            server_default=text("now()"),
            onupdate=datetime.now,
        )
        last_login_at: Mapped[datetime | None] = mapped_column(
            TIMESTAMP(timezone=True), nullable=True
        )
        referral_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
        referred_by: Mapped[uuid.UUID | None] = mapped_column(
            UUID(as_uuid=True),
            ForeignKey(f"{auth_schema}.users.id", ondelete="SET NULL"),
            nullable=True,
        )
        region: Mapped[str | None] = mapped_column(String(5), nullable=True)

    User.__name__ = "User"
    User.__qualname__ = "User"
    return User
