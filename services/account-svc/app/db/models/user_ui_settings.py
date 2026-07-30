"""UserUiSettings ORM model - replaces fmx_keybindings, fmx_tool_view, useResize localStorage."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


class UserUiSettings(Base):
    __tablename__ = "user_ui_settings"
    __table_args__ = {"schema": settings.DB_SCHEMA_AUTH}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{settings.DB_SCHEMA_AUTH}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tool_view: Mapped[str] = mapped_column(
        String(10), nullable=False, default="grid", server_default=text("'grid'")
    )
    # Sparse map of custom keybinding overrides: {shortcut_id: {keys, ctrl?, shift?, alt?}}
    keybindings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Persisted panel sizes: {panel_key: size_px}
    panel_sizes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Whether the user has been through (or dismissed) the starter-kit
    # onboarding modal. Backfilled true in 0004 for anyone with a persona.
    onboarding_seen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Ordered tool-panel chip row: [{type: view|group|custom_group, id}].
    # [] = never customized - the client applies its default row.
    sidebar_chips: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.now
    )

    user: Mapped["User"] = relationship(back_populates="ui_settings")
