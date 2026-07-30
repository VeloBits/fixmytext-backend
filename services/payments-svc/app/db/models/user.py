"""User ORM model for payments-svc - lives in the 'auth' schema.

The column set is defined once in fixmytext_shared.db.models.user via the
make_user_class() factory.  Service-specific billing relationships are attached
here after the class is created.
"""

from fixmytext_shared.db.models.user import make_user_class
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.db.session import Base

User = make_user_class(Base, settings.DB_SCHEMA_AUTH)

# ── Billing-schema relationships (payments-svc only) ──────────────────────────
User.subscriptions = relationship(
    "Subscription", back_populates="user", cascade="all, delete-orphan"
)
User.payment_events = relationship(
    "PaymentEvent", back_populates="user", cascade="all, delete-orphan"
)
User.billing_passes = relationship(
    "BillingUserPass", back_populates="user", cascade="all, delete-orphan"
)
User.billing_credits = relationship(
    "BillingUserCredit", back_populates="user", cascade="all, delete-orphan"
)

__all__ = ["User"]
