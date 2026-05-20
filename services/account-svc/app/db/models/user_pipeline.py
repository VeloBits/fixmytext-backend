"""UserPipeline and UserPipelineStep ORM models — replaces saved_pipelines JSONB."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class UserPipeline(Base):
    __tablename__ = "user_pipelines"
    __table_args__ = (
        Index(
            "ix_user_pipelines_user_active",
            "user_id",
            postgresql_where=text("is_active = true"),
        ),
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
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.now
    )

    user: Mapped["User"] = relationship(back_populates="pipelines")
    steps: Mapped[list["UserPipelineStep"]] = relationship(
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="UserPipelineStep.step_order",
    )


class UserPipelineStep(Base):
    __tablename__ = "user_pipeline_steps"
    __table_args__ = (
        Index("ix_user_pipeline_steps_pipeline", "pipeline_id", "step_order"),
        Index(
            "uq_pipeline_step_order",
            "pipeline_id",
            "step_order",
            unique=True,
        ),
        {"schema": settings.DB_SCHEMA_ACTIVITY},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{settings.DB_SCHEMA_ACTIVITY}.user_pipelines.id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_label: Mapped[str] = mapped_column(String(200), nullable=False)
    # Per-step configuration blob (e.g. {target_language: 'es'} for translate step)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    pipeline: Mapped["UserPipeline"] = relationship(back_populates="steps")
