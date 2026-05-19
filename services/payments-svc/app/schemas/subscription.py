"""Pydantic schemas for subscription/billing."""

from pydantic import BaseModel


class SubscriptionStatus(BaseModel):
    """Current subscription status and usage summary for the user."""

    tier: str
    tool_uses_today: dict = {}
    free_uses_per_tool: int = 3
    daily_login_bonus: bool = False
    credit_balance: int = 0
    active_passes_count: int = 0
    region: str | None = None


class RazorpayProOrderResponse(BaseModel):
    """Response after creating a Razorpay order for Pro subscription."""

    order_id: str
    amount: int
    currency: str
    key_id: str
    user_email: str
    user_name: str


class RazorpayProVerifyRequest(BaseModel):
    """Request to verify a Razorpay payment for Pro subscription."""

    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
