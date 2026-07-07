"""User ORM model for account-svc — lives in the 'auth' schema.

The column set is defined once in fixmytext_shared.db.models.user via the
make_user_class() factory.  Service-specific activity relationships are attached
here after the class is created.
"""

from fixmytext_shared.db.models.user import make_user_class
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.db.session import Base

User = make_user_class(Base, settings.DB_SCHEMA_AUTH)

# ── Activity-schema relationships (account-svc only) ──────────────────────────
User.preferences = relationship(
    "UserPreferences", back_populates="user", cascade="all, delete-orphan"
)
User.ui_settings = relationship(
    "UserUiSettings", back_populates="user", cascade="all, delete-orphan"
)
User.gamification = relationship(
    "UserGamification", back_populates="user", cascade="all, delete-orphan"
)
User.templates = relationship(
    "UserTemplate", back_populates="user", cascade="all, delete-orphan"
)
User.operation_history = relationship(
    "OperationHistory", back_populates="user", cascade="all, delete-orphan"
)
User.pipelines = relationship(
    "UserPipeline", back_populates="user", cascade="all, delete-orphan"
)

__all__ = ["User"]
