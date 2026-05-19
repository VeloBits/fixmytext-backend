"""Pydantic schemas for passes, credits, and tool access."""

from datetime import datetime

from pydantic import BaseModel, Field

# ── Catalog ──────────────────────────────────────────────────────────────────


class PassCatalogItem(BaseModel):
    """A single pass available for purchase in the catalog."""

    id: str
    name: str
    subtitle: str
    tools: int
    uses_per_day: int
    duration_days: int
    price: int
    currency: str
    symbol: str


class CreditPackItem(BaseModel):
    """A single credit pack available for purchase in the catalog."""

    id: str
    name: str
    credits: int
    price: int
    currency: str
    symbol: str


class CatalogResponse(BaseModel):
    """Full catalog of available passes and credit packs."""

    passes: list[PassCatalogItem]
    credit_packs: list[CreditPackItem]
    region: str


# ── Active Passes & Credits ──────────────────────────────────────────────────


class ActivePass(BaseModel):
    """An active (non-expired) pass belonging to the user."""

    id: str
    pass_id: str
    name: str
    tool_ids: list[str]
    tools_count: int
    uses_per_day: int
    uses_today: int
    expires_at: datetime
    source: str


class ActiveCredit(BaseModel):
    """A credit pack with remaining balance belonging to the user."""

    id: str
    credits_remaining: int
    credits_total: int
    source: str


class ActiveResponse(BaseModel):
    """Response containing active passes, credits, and total credit balance."""

    passes: list[ActivePass]
    credits: list[ActiveCredit]
    total_credits: int


# ── Razorpay Order / Verify ──────────────────────────────────────────────────


class PassOrderRequest(BaseModel):
    """Request to create a Razorpay order for a pass purchase."""

    pass_id: str = Field(..., description="Catalog pass ID e.g. 'day_triple'")
    tool_ids: list[str] = Field(default=[], description="Selected tool IDs")
    region: str = Field(
        default="", description="Browser-detected region (IN, US, GB, EU)"
    )


class CreditOrderRequest(BaseModel):
    """Request to create a Razorpay order for a credit pack purchase."""

    pack_id: str = Field(..., description="Credit pack ID e.g. 'credits_15'")
    region: str = Field(default="", description="Browser-detected region")


class RazorpayOrderResponse(BaseModel):
    """Response after creating a Razorpay order, with details needed by the client."""

    order_id: str
    amount: int
    currency: str
    key_id: str
    user_email: str
    user_name: str


class RazorpayVerifyRequest(BaseModel):
    """Request to verify a Razorpay payment (pass or credit)."""

    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    item_id: str
    item_type: str = Field(
        ...,
        pattern="^(pass|credit)$",
        description="Must be 'pass' or 'credit'",
    )
    tool_ids: list[str] = Field(
        default_factory=list,
        description="Required tool IDs for pass purchases",
    )


# ── Spin ─────────────────────────────────────────────────────────────────────


class SpinResult(BaseModel):
    """Result of a weekly spin-the-wheel attempt."""

    reward_type: str
    amount: int | None = None
    pass_id: str | None = None
    pass_name: str | None = None
    message: str


# ── Referral ─────────────────────────────────────────────────────────────────


class ClaimReferralRequest(BaseModel):
    """Request to claim a referral code."""

    code: str = Field(
        ..., min_length=1, max_length=20, description="Referral code to claim"
    )


class ReferralCodeResponse(BaseModel):
    """Response containing the user's referral code and shareable URL."""

    referral_code: str
    referral_url: str
