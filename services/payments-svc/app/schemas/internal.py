"""Schemas for internal service-to-service endpoints (entitlement gate)."""

from pydantic import BaseModel


class CheckAccessRequest(BaseModel):
    """Entitlement check forwarded by text-svc / ai-svc before running a tool."""

    tool_id: str
    tool_type: str = "local"  # "local" | "ai" | "drawer"
    principal_type: str  # "user" | "visitor"
    # Authenticated principal (Keycloak sub + claims for JIT provisioning).
    user_id: str | None = None
    email: str | None = None
    email_verified: bool = False
    # Anonymous principal — real client IP + UA, server-observed by the caller.
    # The visitor quota key is derived from these server-side (never the
    # client-supplied X-Visitor-Id), closing the fingerprint-reset gap.
    ip_address: str | None = None
    user_agent: str | None = None


class CheckAccessResponse(BaseModel):
    """Entitlement decision. allowed=False is a normal 200 (quota exhausted)."""

    allowed: bool
    reason: str  # free | pro | pass | credit | blocked
    message: str | None = None
    uses_today: int | None = None
    max_free: int | None = None
    credits_remaining: int | None = None
