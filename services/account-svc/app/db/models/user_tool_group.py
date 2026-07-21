"""UserToolGroup and UserToolGroupItem ORM models — user-created named tool groups."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


class UserToolGroup(Base):
    __tablename__ = "user_tool_groups"
    __table_args__ = (
        Index("ix_user_tool_groups_user_id", "user_id"),
        UniqueConstraint("user_id", "name", name="uq_user_tool_groups_user_name"),
        {"schema": settings.DB_SCHEMA_ACTIVITY},
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
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.now
    )

    items: Mapped[list["UserToolGroupItem"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="UserToolGroupItem.sort_order",
    )


class UserToolGroupItem(Base):
    __tablename__ = "user_tool_group_items"
    __table_args__ = (
        Index("ix_user_tool_group_items_group_id", "group_id"),
        {"schema": settings.DB_SCHEMA_ACTIVITY},
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{settings.DB_SCHEMA_ACTIVITY}.user_tool_groups.id", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    tool_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    sort_order: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    group: Mapped["UserToolGroup"] = relationship(back_populates="items")
