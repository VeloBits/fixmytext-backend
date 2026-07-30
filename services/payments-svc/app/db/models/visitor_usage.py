"""VisitorUsage ORM model - server-side trial tracking for unauthenticated users."""

import uuid
from datetime import datetime

from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import INET, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base


class VisitorUsage(Base):
    __tablename__ = "visitor_usage"
    __table_args__ = (
        Index("ix_visitor_usage_fingerprint", "fingerprint"),
        Index(
            "ix_visitor_usage_ip_inet",
            "ip_address",
            postgresql_using="gist",
            postgresql_ops={"ip_address": "inet_ops"},
            postgresql_where=text("ip_address IS NOT NULL"),
        ),
        {"schema": settings.DB_SCHEMA_AUTH},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
