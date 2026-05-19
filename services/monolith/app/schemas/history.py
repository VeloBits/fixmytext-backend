"""Pydantic schemas for operation history."""

from pydantic import BaseModel, Field


class HistoryCreate(BaseModel):
    """Schema for recording a new operation history entry."""

    tool_id: str = Field(..., min_length=1, max_length=100)
    tool_label: str = Field(..., min_length=1, max_length=200)
    tool_type: str = Field(..., min_length=1, max_length=20)
    input_preview: str = Field(..., max_length=500)
    output_preview: str = Field(..., max_length=500)
    input_length: int = Field(..., ge=0)
    output_length: int = Field(..., ge=0)
    status: str = Field("success", max_length=20)


class HistoryResponse(BaseModel):
    """A single history entry as returned by the API."""

    id: str
    tool_id: str
    tool_label: str
    tool_type: str
    input_preview: str
    output_preview: str
    input_length: int
    output_length: int
    status: str
    created_at: str


class HistoryListResponse(BaseModel):
    """Paginated list of history entries."""

    items: list[HistoryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class HistoryStatsResponse(BaseModel):
    """Aggregated statistics across all history entries."""

    total_operations: int
    tools_breakdown: dict[str, int]  # tool_id -> count
    recent_tools: list[str]  # last 10 unique tool_ids
