"""Pydantic schemas for user preferences, gamification, templates, ui-settings, favorites, tool-stats, pipelines."""

from pydantic import BaseModel, Field

# ── Preferences ──────────────────────────────────────────────────────────────


class PreferencesResponse(BaseModel):
    """Current user preference values."""

    theme: str = "dark"
    persona: str | None = None
    theme_skin: str | None = None


class PreferencesUpdate(BaseModel):
    """Partial update for user preferences. All fields optional."""

    theme: str | None = Field(None, max_length=10)
    persona: str | None = Field(None, max_length=50)
    theme_skin: str | None = Field(None, max_length=50)


# ── Gamification ─────────────────────────────────────────────────────────────


class GamificationResponse(BaseModel):
    """Current gamification state for a user."""

    xp: int = 0
    streak_current: int = 0
    streak_last_date: str | None = None
    total_ops: int = 0
    total_chars: int = 0
    achievements: list[str] = []
    completed_quests: list[str] = []
    daily_quest_id: str | None = None
    daily_quest_date: str | None = None
    daily_quest_completed: bool = False


class GamificationUpdate(BaseModel):
    """Partial update for gamification state. All fields optional."""

    xp: int | None = None
    streak_current: int | None = None
    streak_last_date: str | None = None
    total_ops: int | None = None
    total_chars: int | None = None
    achievements: list[str] | None = None
    completed_quests: list[str] | None = None
    daily_quest_id: str | None = None
    daily_quest_date: str | None = None
    daily_quest_completed: bool | None = None


# ── Templates ────────────────────────────────────────────────────────────────


class TemplateBase(BaseModel):
    """Base fields shared across template schemas."""

    name: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=1)
    tool_id: str | None = Field(None, max_length=100)


class TemplateCreate(TemplateBase):
    """Schema for creating a new template."""


class TemplateUpdate(BaseModel):
    """Schema for updating a template. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=200)
    text: str | None = Field(None, min_length=1)
    tool_id: str | None = Field(None, max_length=100)


class TemplateResponse(BaseModel):
    """Template as returned by the API."""

    id: str
    name: str
    text: str
    tool_id: str | None = None
    created_at: str
    updated_at: str


# ── UI Settings ───────────────────────────────────────────────────────────────


class UiSettingsBase(BaseModel):
    """Base fields shared across UI settings schemas."""

    tool_view: str = "grid"
    keybindings: dict = {}
    panel_sizes: dict = {}


class UiSettingsResponse(UiSettingsBase):
    """Current UI settings for the user."""


class UiSettingsUpdate(BaseModel):
    """Partial update for UI settings. All fields optional."""

    tool_view: str | None = Field(None, max_length=10)
    keybindings: dict | None = None
    panel_sizes: dict | None = None


# ── Favorites ─────────────────────────────────────────────────────────────────


class FavoriteToolItem(BaseModel):
    """A single favorited tool with its sort position."""

    tool_id: str
    sort_order: int


class FavoritesResponse(BaseModel):
    """List of the user's favorited tools."""

    favorites: list[FavoriteToolItem]


# ── Tool Stats ────────────────────────────────────────────────────────────────


class ToolStatItem(BaseModel):
    """Usage statistics for a single tool."""

    tool_id: str
    total_uses: int
    last_used_at: str


class ToolStatsResponse(BaseModel):
    """Aggregated tool usage statistics for the user."""

    stats: list[ToolStatItem]


# ── Pipelines ─────────────────────────────────────────────────────────────────


class PipelineStepResponse(BaseModel):
    """A single step within a pipeline, as returned by the API."""

    id: str
    step_order: int
    tool_id: str
    tool_label: str
    config: dict | None = None


class PipelineResponse(BaseModel):
    """A full pipeline with all its steps, as returned by the API."""

    id: str
    name: str
    description: str | None = None
    steps: list[PipelineStepResponse]
    created_at: str
    updated_at: str


class PipelineStepIn(BaseModel):
    """Input schema for a single pipeline step."""

    step_order: int
    tool_id: str = Field(..., max_length=100)
    tool_label: str = Field(..., max_length=200)
    config: dict | None = None


class PipelineCreate(BaseModel):
    """Schema for creating a new pipeline."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)
    steps: list[PipelineStepIn] = []


class PipelineUpdate(BaseModel):
    """Schema for updating a pipeline. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)
    steps: list[PipelineStepIn] | None = None


# ── Discovered Tools ─────────────────────────────────────────────────────────


class DiscoveredToolItem(BaseModel):
    """A single tool the user has discovered."""

    tool_id: str
    discovered_at: str


class DiscoveredToolsResponse(BaseModel):
    """List of tools the user has discovered."""

    tools: list[DiscoveredToolItem]
    count: int


# ── Spin History ─────────────────────────────────────────────────────────────


class SpinHistoryItem(BaseModel):
    """A single spin-the-wheel result entry."""

    spin_date: str
    reward_type: str
    reward_ref: str | None = None
    iso_week: int


class SpinHistoryResponse(BaseModel):
    """List of the user's spin history entries."""

    spins: list[SpinHistoryItem]
