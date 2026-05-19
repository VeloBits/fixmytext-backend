"""ORM models package — re-exports all models for convenience."""

# ── Core auth models ──────────────────────────────────────────────────────────
# ── Billing models ────────────────────────────────────────────────────────────
from app.db.models.billing_catalog import (
    CreditPackCatalog,
    CreditPackPrice,
    PassCatalog,
    PassCatalogPrice,
)
from app.db.models.billing_credit import BillingUserCredit
from app.db.models.billing_pass import BillingUserPass, UserPassTool
from app.db.models.billing_subscription import PaymentEvent, Subscription

# ── Activity models ───────────────────────────────────────────────────────────
from app.db.models.gamification import UserGamification
from app.db.models.operation_history import OperationHistory
from app.db.models.preferences import UserPreferences
from app.db.models.shared_result import SharedResult
from app.db.models.template import UserTemplate
from app.db.models.user import User
from app.db.models.user_daily_login import UserDailyLogin
from app.db.models.user_discovered_tool import UserDiscoveredTool
from app.db.models.user_favorite_tool import UserFavoriteTool
from app.db.models.user_pipeline import UserPipeline, UserPipelineStep
from app.db.models.user_spin_log import UserSpinLog
from app.db.models.user_tool_stats import UserToolStats
from app.db.models.user_tool_usage import UserToolUsage
from app.db.models.user_ui_settings import UserUiSettings
from app.db.models.visitor_tool_usage import VisitorToolUsage
from app.db.models.visitor_usage import VisitorUsage

__all__ = [
    # auth
    "User",
    "UserPreferences",
    "UserUiSettings",
    "UserToolUsage",
    "UserDailyLogin",
    "UserSpinLog",
    "VisitorUsage",
    "VisitorToolUsage",
    # billing
    "PassCatalog",
    "PassCatalogPrice",
    "CreditPackCatalog",
    "CreditPackPrice",
    "Subscription",
    "PaymentEvent",
    "BillingUserPass",
    "UserPassTool",
    "BillingUserCredit",
    # activity
    "UserGamification",
    "UserToolStats",
    "UserDiscoveredTool",
    "UserFavoriteTool",
    "UserPipeline",
    "UserPipelineStep",
    "UserTemplate",
    "OperationHistory",
    "SharedResult",
]
