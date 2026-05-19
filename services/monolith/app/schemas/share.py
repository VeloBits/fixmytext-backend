"""Pydantic schemas for shared results."""

from pydantic import BaseModel, Field


class ShareCreate(BaseModel):
    """Schema for creating a shareable link from a tool's output."""

    tool_id: str = Field(..., min_length=1, max_length=100)
    tool_label: str = Field(..., min_length=1, max_length=200)
    output_text: str = Field(..., min_length=1, max_length=50_000)


class ShareResponse(BaseModel):
    """Response after successfully creating a shareable link."""

    id: str
    share_url: str


class SharedResultView(BaseModel):
    """Public view of a shared result (no auth required)."""

    id: str
    tool_id: str
    tool_label: str
    output_text: str
    created_at: str
