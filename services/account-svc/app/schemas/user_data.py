"""Pydantic schemas for user data: preferences, templates, ui-settings, favorites, tool groups."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

# ── Preferences ──────────────────────────────────────────────────────────────


class PreferencesResponse(BaseModel):
    """Current user preference values.

    `persona` is transitional read-only legacy state (feature replaced by
    custom tool groups 2026-07-14): stale deployed bundles still read it, and
    PreferencesUpdate no longer accepts it. Remove the field together with the
    column drop migration.

    `auto_run` defaults to False: manual Run is the default execution mode, so
    a stale bundle (or a user who never toggled it) gets the safe, quota-
    preserving behavior.
    """

    theme: str = "dark"
    persona: str | None = None
    theme_skin: str | None = None
    auto_run: bool = False


class PreferencesUpdate(BaseModel):
    """Partial update for user preferences. All fields optional.

    A `persona` key sent by a stale bundle is silently ignored (pydantic
    drops unknown fields) - deliberate transitional behavior.
    """

    theme: str | None = Field(None, max_length=10)
    theme_skin: str | None = Field(None, max_length=50)
    auto_run: bool | None = None


# ── Templates ────────────────────────────────────────────────────────────────


class TemplateBase(BaseModel):
    """Base fields shared across template schemas."""

    name: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=1, max_length=50_000)
    tool_id: str | None = Field(None, max_length=100)


class TemplateCreate(TemplateBase):
    """Schema for creating a new template."""


class TemplateUpdate(BaseModel):
    """Schema for updating a template. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=200)
    text: str | None = Field(None, min_length=1, max_length=50_000)
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


class SidebarChipItem(BaseModel):
    """One tool-panel sidebar chip: a smart view or a group filter.

    `view` ids are client-defined (all/pinned/recent/suggested), `group` ids
    are catalog TOOL_GROUPS ids, `custom_group` ids are user_tool_groups UUIDs.
    The server stays structural - semantics (e.g. 'all' never removable) are
    enforced by the client that owns the vocabulary.
    """

    type: Literal["view", "group", "custom_group"]
    id: str = Field(..., min_length=1, max_length=100)


def _dedupe_chips(chips: list[SidebarChipItem]) -> list[SidebarChipItem]:
    """Order-preserving dedupe by (type, id) - makes PUT retries idempotent."""
    seen: set[tuple[str, str]] = set()
    out: list[SidebarChipItem] = []
    for chip in chips:
        key = (chip.type, chip.id)
        if key not in seen:
            seen.add(key)
            out.append(chip)
    return out


class UiSettingsBase(BaseModel):
    """Base fields shared across UI settings schemas."""

    tool_view: str = "grid"
    keybindings: dict = {}
    panel_sizes: dict = {}
    onboarding_seen: bool = False
    sidebar_chips: list[SidebarChipItem] = []


class UiSettingsResponse(UiSettingsBase):
    """Current UI settings for the user."""


class UiSettingsUpdate(BaseModel):
    """Partial update for UI settings. All fields optional."""

    tool_view: str | None = Field(None, max_length=10)
    keybindings: dict | None = None
    panel_sizes: dict | None = None
    onboarding_seen: bool | None = None
    sidebar_chips: list[SidebarChipItem] | None = Field(None, max_length=40)

    @field_validator("sidebar_chips")
    @classmethod
    def dedupe_sidebar_chips(
        cls, v: list[SidebarChipItem] | None
    ) -> list[SidebarChipItem] | None:
        return _dedupe_chips(v) if v is not None else v


# ── Favorites ─────────────────────────────────────────────────────────────────


class FavoriteToolItem(BaseModel):
    """A single favorited tool with its sort position."""

    tool_id: str
    sort_order: int


class FavoritesResponse(BaseModel):
    """List of the user's favorited tools."""

    favorites: list[FavoriteToolItem]


# ── Tool Groups ───────────────────────────────────────────────────────────────


class ToolGroupItemOut(BaseModel):
    """A single tool within a group, with its sort position."""

    tool_id: str
    sort_order: int


class ToolGroupResponse(BaseModel):
    """A named tool group with its tools, as returned by the API."""

    id: str
    name: str
    sort_order: int
    tools: list[ToolGroupItemOut]
    created_at: str
    updated_at: str


class ToolGroupsResponse(BaseModel):
    """All of the user's tool groups in display order."""

    groups: list[ToolGroupResponse]


class ToolGroupCreate(BaseModel):
    """Schema for creating a tool group, optionally pre-filled with tools."""

    name: str = Field(..., min_length=1, max_length=100)
    tool_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default=[], max_length=50
    )


class ToolGroupUpdate(BaseModel):
    """Schema for renaming a tool group."""

    name: str | None = Field(None, min_length=1, max_length=100)


class ToolGroupItemsUpdate(BaseModel):
    """Schema for replacing a group's tools with an explicit ordered list.

    The array position IS the sort order - one call covers reorder, bulk add,
    and bulk remove (drag-and-drop sends the full list after every move).
    """

    tool_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        ..., max_length=50
    )


class ToolGroupOrderUpdate(BaseModel):
    """Schema for reordering the user's tool groups by id.

    Groups listed get sort_order = array position; any of the user's groups
    not listed keep their relative order after the listed ones. Unknown or
    foreign ids are ignored (optimistic clients may hold stale ids).
    """

    group_ids: list[str] = Field(..., min_length=1, max_length=20)


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
    steps: list[PipelineStepIn] = Field(default=[], max_length=50)


class PipelineUpdate(BaseModel):
    """Schema for updating a pipeline. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)
    steps: list[PipelineStepIn] | None = Field(None, max_length=50)


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
