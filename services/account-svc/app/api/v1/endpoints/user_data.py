"""User data endpoints: preferences, templates, ui-settings, favorites, tool-groups, tool-stats.

Covers all per-user data CRUD operations including paginated listing of
templates and pipelines, favorite and tool-group management, and UI
preferences. Also hosts the transitional no-op gamification stubs (feature
removed 2026-07-13).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.db.models import (
    User,
    UserDiscoveredTool,
    UserFavoriteTool,
    UserPipeline,
    UserPipelineStep,
    UserPreferences,
    UserSpinLog,
    UserTemplate,
    UserToolGroup,
    UserToolGroupItem,
    UserToolStats,
    UserUiSettings,
)
from app.db.session import get_db
from app.schemas.user_data import (
    DiscoveredToolItem,
    DiscoveredToolsResponse,
    FavoritesResponse,
    FavoriteToolItem,
    PipelineCreate,
    PipelineResponse,
    PipelineStepResponse,
    PipelineUpdate,
    PreferencesResponse,
    PreferencesUpdate,
    SpinHistoryItem,
    SpinHistoryResponse,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
    ToolGroupCreate,
    ToolGroupItemOut,
    ToolGroupItemsUpdate,
    ToolGroupOrderUpdate,
    ToolGroupResponse,
    ToolGroupsResponse,
    ToolGroupUpdate,
    ToolStatItem,
    ToolStatsResponse,
    UiSettingsResponse,
    UiSettingsUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["User Data"])


# ── Preferences ──────────────────────────────────────────────────────────────


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's preferences (theme, persona, skin)."""
    prefs = await db.get(UserPreferences, user.id)
    if not prefs:
        return PreferencesResponse()
    return PreferencesResponse(
        theme=prefs.theme, persona=prefs.persona, theme_skin=prefs.theme_skin
    )


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: PreferencesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's preferences (partial update)."""
    prefs = await db.get(UserPreferences, user.id)
    if not prefs:
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(prefs, key, value)

    await db.commit()
    await db.refresh(prefs)
    return PreferencesResponse(
        theme=prefs.theme, persona=prefs.persona, theme_skin=prefs.theme_skin
    )


# ── Gamification (transitional no-op stubs) ──────────────────────────────────
#
# The gamification feature was removed on 2026-07-13. The frontend soft-delete
# is already deployed and no longer calls these routes; the backing table
# (activity.user_gamification) is dropped in migration 0003. These DB-free
# stubs exist ONLY so stale cached SPA bundles (pre-soft-delete) don't hit
# 404s and surface error toasts. The auth dependency is deliberately kept so
# the routes don't become anonymous probes. Every hit logs a WARNING
# ("stale_gamification_call") — delete both stubs in a later release once
# logs show zero hits.

_GAMIFICATION_ZERO_STATE = {
    "xp": 0,
    "streak_current": 0,
    "streak_last_date": None,
    "total_ops": 0,
    "total_chars": 0,
    "achievements": [],
    "completed_quests": [],
    "daily_quest_id": None,
    "daily_quest_date": None,
    "daily_quest_completed": False,
}


@router.get("/gamification")
async def get_gamification(user: User = Depends(get_current_user)) -> dict:
    """Transitional stub — gamification removed; returns a static zero-state."""
    logger.warning(
        "stale_gamification_call: route=%s sub=%s",
        "GET /user/gamification",
        user.keycloak_id,
    )
    return dict(_GAMIFICATION_ZERO_STATE)


@router.put("/gamification")
async def update_gamification(
    request: Request,  # noqa: ARG001 — accepts (and ignores) any body
    user: User = Depends(get_current_user),
) -> dict:
    """Transitional stub — accepts any body, persists nothing, returns zero-state."""
    logger.warning(
        "stale_gamification_call: route=%s sub=%s",
        "PUT /user/gamification",
        user.keycloak_id,
    )
    return dict(_GAMIFICATION_ZERO_STATE)


# ── Templates ────────────────────────────────────────────────────────────────


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
):
    """List the authenticated user's saved templates with pagination.

    Returns templates ordered newest-first so the most recently created
    template appears at the top of the list.
    """
    result = await db.execute(
        select(UserTemplate)
        .where(UserTemplate.user_id == user.id, UserTemplate.is_deleted == False)  # noqa: E712
        .order_by(desc(UserTemplate.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    templates = result.scalars().all()
    return [
        TemplateResponse(
            id=str(t.id),
            name=t.name,
            text=t.text,
            tool_id=t.tool_id,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
        )
        for t in templates
    ]


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    body: TemplateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new saved template for the authenticated user."""
    template = UserTemplate(
        user_id=user.id,
        keycloak_sub=str(user.keycloak_id),
        name=body.name,
        text=body.text,
        tool_id=body.tool_id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return TemplateResponse(
        id=str(template.id),
        name=template.name,
        text=template.text,
        tool_id=template.tool_id,
        created_at=template.created_at.isoformat(),
        updated_at=template.updated_at.isoformat(),
    )


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing template owned by the authenticated user."""
    template = await db.get(UserTemplate, template_id)
    if not template or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="Template not found")

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(template, key, value)

    await db.commit()
    await db.refresh(template)
    return TemplateResponse(
        id=str(template.id),
        name=template.name,
        text=template.text,
        tool_id=template.tool_id,
        created_at=template.created_at.isoformat(),
        updated_at=template.updated_at.isoformat(),
    )


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a template owned by the authenticated user."""
    template = await db.get(UserTemplate, template_id)
    if not template or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.delete(template)
    await db.commit()


# ── UI Settings ───────────────────────────────────────────────────────────────


@router.get("/ui-settings", response_model=UiSettingsResponse)
async def get_ui_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's UI settings (tool view, keybindings, panel sizes)."""
    row = await db.get(UserUiSettings, user.id)
    if not row:
        return UiSettingsResponse()
    return UiSettingsResponse(
        tool_view=row.tool_view,
        keybindings=row.keybindings or {},
        panel_sizes=row.panel_sizes or {},
        onboarding_seen=row.onboarding_seen,
        sidebar_chips=row.sidebar_chips or [],
    )


@router.put("/ui-settings", response_model=UiSettingsResponse)
async def update_ui_settings(
    body: UiSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's UI settings (partial update)."""
    row = await db.get(UserUiSettings, user.id)
    if not row:
        row = UserUiSettings(user_id=user.id)
        db.add(row)

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return UiSettingsResponse(
        tool_view=row.tool_view,
        keybindings=row.keybindings or {},
        panel_sizes=row.panel_sizes or {},
        onboarding_seen=row.onboarding_seen,
        sidebar_chips=row.sidebar_chips or [],
    )


# ── Favorites ─────────────────────────────────────────────────────────────────


@router.get("/favorites", response_model=FavoritesResponse)
async def get_favorites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's favorited tools sorted by display order."""
    result = await db.execute(
        select(UserFavoriteTool)
        .where(UserFavoriteTool.user_id == user.id)
        .order_by(UserFavoriteTool.sort_order)
    )
    rows = result.scalars().all()
    return FavoritesResponse(
        favorites=[
            FavoriteToolItem(tool_id=r.tool_id, sort_order=r.sort_order) for r in rows
        ]
    )


@router.post("/favorites/{tool_id}", status_code=201)
async def add_favorite(
    tool_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a tool to the authenticated user's favorites list.

    Idempotent: returns the existing entry if the tool is already favorited.
    """
    existing = await db.get(UserFavoriteTool, (user.id, tool_id))
    if existing:
        return JSONResponse(
            content={"tool_id": tool_id, "sort_order": existing.sort_order},
            status_code=200,
        )

    max_result = await db.execute(
        select(func.max(UserFavoriteTool.sort_order)).where(
            UserFavoriteTool.user_id == user.id
        )
    )
    max_order = max_result.scalar() or -1

    fav = UserFavoriteTool(user_id=user.id, tool_id=tool_id, sort_order=max_order + 1)
    db.add(fav)
    await db.commit()
    return {"tool_id": tool_id, "sort_order": max_order + 1}


@router.delete("/favorites/{tool_id}", status_code=204)
async def remove_favorite(
    tool_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a tool from the authenticated user's favorites list."""
    fav = await db.get(UserFavoriteTool, (user.id, tool_id))
    if fav:
        await db.delete(fav)
        await db.commit()


# ── Tool Groups ─────────────────────────────────────────────────────────────

MAX_TOOL_GROUPS_PER_USER = 20
MAX_TOOLS_PER_GROUP = 50


def _group_to_response(g: UserToolGroup) -> ToolGroupResponse:
    return ToolGroupResponse(
        id=str(g.id),
        name=g.name,
        sort_order=g.sort_order,
        tools=[
            ToolGroupItemOut(tool_id=i.tool_id, sort_order=i.sort_order)
            for i in sorted(g.items, key=lambda i: i.sort_order)
        ],
        created_at=g.created_at.isoformat(),
        updated_at=g.updated_at.isoformat(),
    )


async def _get_owned_group(
    db: AsyncSession, group_id: uuid.UUID, user_id: uuid.UUID
) -> UserToolGroup:
    """Load a group with items, or 404 if it doesn't exist / isn't the user's."""
    result = await db.execute(
        select(UserToolGroup)
        .where(UserToolGroup.id == group_id, UserToolGroup.user_id == user_id)
        .options(selectinload(UserToolGroup.items))
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Tool group not found")
    return group


@router.get("/tool-groups", response_model=ToolGroupsResponse)
async def list_tool_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all of the authenticated user's tool groups in display order."""
    result = await db.execute(
        select(UserToolGroup)
        .where(UserToolGroup.user_id == user.id)
        .options(selectinload(UserToolGroup.items))
        .order_by(UserToolGroup.sort_order, UserToolGroup.created_at)
    )
    return ToolGroupsResponse(
        groups=[_group_to_response(g) for g in result.scalars().all()]
    )


@router.post("/tool-groups", response_model=ToolGroupResponse, status_code=201)
async def create_tool_group(
    body: ToolGroupCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a named tool group, optionally pre-filled with tools.

    Idempotent by name: if the user already has a group with this name, the
    existing group is returned unchanged (200) — tool_ids are NOT merged in.
    This keeps guest-adoption retries and double-clicked starter-kit cards
    from erroring or duplicating.
    """
    existing_result = await db.execute(
        select(UserToolGroup)
        .where(UserToolGroup.user_id == user.id, UserToolGroup.name == body.name)
        .options(selectinload(UserToolGroup.items))
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return JSONResponse(
            content=_group_to_response(existing).model_dump(), status_code=200
        )

    count_result = await db.execute(
        select(func.count()).where(UserToolGroup.user_id == user.id)
    )
    if (count_result.scalar() or 0) >= MAX_TOOL_GROUPS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Tool group limit reached ({MAX_TOOL_GROUPS_PER_USER})",
        )

    max_result = await db.execute(
        select(func.max(UserToolGroup.sort_order)).where(
            UserToolGroup.user_id == user.id
        )
    )
    max_order = max_result.scalar()
    next_order = 0 if max_order is None else max_order + 1

    group = UserToolGroup(user_id=user.id, name=body.name, sort_order=next_order)
    db.add(group)
    await db.flush()

    deduped: list[str] = []
    for tool_id in body.tool_ids:
        if tool_id not in deduped:
            deduped.append(tool_id)
    for i, tool_id in enumerate(deduped[:MAX_TOOLS_PER_GROUP]):
        db.add(UserToolGroupItem(group_id=group.id, tool_id=tool_id, sort_order=i))

    await db.commit()
    result = await db.execute(
        select(UserToolGroup)
        .where(UserToolGroup.id == group.id)
        .options(selectinload(UserToolGroup.items))
    )
    return _group_to_response(result.scalar_one())


# NOTE: registered before the /{group_id} routes — "order" must not be parsed
# as a group_id UUID (FastAPI matches routes in declaration order).
@router.put("/tool-groups/order", response_model=ToolGroupsResponse)
async def reorder_tool_groups(
    body: ToolGroupOrderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reorder the authenticated user's tool groups.

    Groups listed in `group_ids` get sort_order = array position; the user's
    remaining groups keep their relative order after the listed ones. Unknown
    and foreign ids are ignored. Idempotent — resending the same list is a
    no-op. Returns all groups in the new display order.
    """
    result = await db.execute(
        select(UserToolGroup)
        .where(UserToolGroup.user_id == user.id)
        .options(selectinload(UserToolGroup.items))
        .order_by(UserToolGroup.sort_order, UserToolGroup.created_at)
    )
    groups = list(result.scalars().all())
    by_id = {str(g.id): g for g in groups}

    ordered: list[UserToolGroup] = []
    for gid in body.group_ids:
        g = by_id.pop(gid, None)
        if g is not None:
            ordered.append(g)
    # Unlisted groups follow, preserving their current relative order.
    ordered.extend(g for g in groups if str(g.id) in by_id)

    for i, g in enumerate(ordered):
        if g.sort_order != i:
            g.sort_order = i

    await db.commit()
    return ToolGroupsResponse(groups=[_group_to_response(g) for g in ordered])


@router.put("/tool-groups/{group_id}", response_model=ToolGroupResponse)
async def rename_tool_group(
    group_id: uuid.UUID,
    body: ToolGroupUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename a tool group owned by the authenticated user."""
    group = await _get_owned_group(db, group_id, user.id)

    if body.name is not None and body.name != group.name:
        dup = await db.execute(
            select(UserToolGroup.id).where(
                UserToolGroup.user_id == user.id, UserToolGroup.name == body.name
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=409, detail="A group with that name already exists"
            )
        group.name = body.name

    await db.commit()
    result = await db.execute(
        select(UserToolGroup)
        .where(UserToolGroup.id == group_id)
        .options(selectinload(UserToolGroup.items))
    )
    return _group_to_response(result.scalar_one())


@router.delete("/tool-groups/{group_id}", status_code=204)
async def delete_tool_group(
    group_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tool group (and its items) owned by the authenticated user."""
    group = await _get_owned_group(db, group_id, user.id)
    await db.delete(group)
    await db.commit()


@router.post("/tool-groups/{group_id}/tools/{tool_id}", status_code=201)
async def add_tool_to_group(
    group_id: uuid.UUID,
    tool_id: str = Path(max_length=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a tool to one of the authenticated user's groups.

    Idempotent: returns the existing entry if the tool is already in the group.
    """
    await _get_owned_group(db, group_id, user.id)

    existing = await db.get(UserToolGroupItem, (group_id, tool_id))
    if existing:
        return JSONResponse(
            content={"tool_id": tool_id, "sort_order": existing.sort_order},
            status_code=200,
        )

    count_result = await db.execute(
        select(func.count()).where(UserToolGroupItem.group_id == group_id)
    )
    if (count_result.scalar() or 0) >= MAX_TOOLS_PER_GROUP:
        raise HTTPException(
            status_code=400,
            detail=f"Tool limit per group reached ({MAX_TOOLS_PER_GROUP})",
        )

    max_result = await db.execute(
        select(func.max(UserToolGroupItem.sort_order)).where(
            UserToolGroupItem.group_id == group_id
        )
    )
    max_order = max_result.scalar()
    next_order = 0 if max_order is None else max_order + 1

    db.add(UserToolGroupItem(group_id=group_id, tool_id=tool_id, sort_order=next_order))
    await db.commit()
    return {"tool_id": tool_id, "sort_order": next_order}


@router.put("/tool-groups/{group_id}/tools", response_model=ToolGroupResponse)
async def set_tool_group_tools(
    group_id: uuid.UUID,
    body: ToolGroupItemsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace a group's tools with an explicit ordered list.

    Array position becomes sort_order, so a single call covers drag-reorder,
    bulk add, and bulk remove. Duplicates keep their first position.
    Idempotent — resending the current list is a no-op.
    """
    group = await _get_owned_group(db, group_id, user.id)

    deduped: list[str] = []
    for tool_id in body.tool_ids:
        if tool_id not in deduped:
            deduped.append(tool_id)
    deduped = deduped[:MAX_TOOLS_PER_GROUP]

    # Diff against existing rows rather than delete-all + reinsert: kept tools
    # just get a new sort_order, so the composite PK never collides in-flush.
    existing = {i.tool_id: i for i in group.items}
    wanted = set(deduped)
    for tool_id, item in existing.items():
        if tool_id not in wanted:
            await db.delete(item)
    for i, tool_id in enumerate(deduped):
        item = existing.get(tool_id)
        if item is not None:
            if item.sort_order != i:
                item.sort_order = i
        else:
            db.add(
                UserToolGroupItem(group_id=group_id, tool_id=tool_id, sort_order=i)
            )

    await db.commit()
    result = await db.execute(
        select(UserToolGroup)
        .where(UserToolGroup.id == group_id)
        .options(selectinload(UserToolGroup.items))
    )
    return _group_to_response(result.scalar_one())


@router.delete("/tool-groups/{group_id}/tools/{tool_id}", status_code=204)
async def remove_tool_from_group(
    group_id: uuid.UUID,
    tool_id: str = Path(max_length=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a tool from one of the authenticated user's groups."""
    await _get_owned_group(db, group_id, user.id)

    item = await db.get(UserToolGroupItem, (group_id, tool_id))
    if item:
        await db.delete(item)
        await db.commit()


# ── Tool Stats ────────────────────────────────────────────────────────────────


@router.get("/tool-stats", response_model=ToolStatsResponse)
async def get_tool_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated tool usage statistics for the authenticated user."""
    result = await db.execute(
        select(UserToolStats)
        .where(UserToolStats.user_id == user.id)
        .order_by(UserToolStats.total_uses.desc())
    )
    rows = result.scalars().all()
    return ToolStatsResponse(
        stats=[
            ToolStatItem(
                tool_id=r.tool_id,
                total_uses=r.total_uses,
                last_used_at=r.last_used_at.isoformat(),
            )
            for r in rows
        ]
    )


# ── Pipelines ─────────────────────────────────────────────────────────────────


def _pipeline_to_response(p: UserPipeline) -> PipelineResponse:
    return PipelineResponse(
        id=str(p.id),
        name=p.name,
        description=p.description,
        steps=[
            PipelineStepResponse(
                id=str(s.id),
                step_order=s.step_order,
                tool_id=s.tool_id,
                tool_label=s.tool_label,
                config=s.config,
            )
            for s in sorted(p.steps, key=lambda s: s.step_order)
        ],
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.get("/pipelines", response_model=list[PipelineResponse])
async def list_pipelines(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
):
    """List the authenticated user's active pipelines with pagination.

    Pipelines are returned newest-first.  Each pipeline eagerly loads its
    steps so the response includes the full pipeline configuration.
    """
    result = await db.execute(
        select(UserPipeline)
        .where(UserPipeline.user_id == user.id, UserPipeline.is_active.is_(True))
        .options(selectinload(UserPipeline.steps))
        .order_by(desc(UserPipeline.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [_pipeline_to_response(p) for p in result.scalars().all()]


@router.post("/pipelines", response_model=PipelineResponse, status_code=201)
async def create_pipeline(
    body: PipelineCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new multi-step pipeline for the authenticated user."""
    pipeline = UserPipeline(
        user_id=user.id, name=body.name, description=body.description
    )
    db.add(pipeline)
    await db.flush()

    for step_in in body.steps:
        db.add(
            UserPipelineStep(
                pipeline_id=pipeline.id,
                step_order=step_in.step_order,
                tool_id=step_in.tool_id,
                tool_label=step_in.tool_label,
                config=step_in.config,
            )
        )

    await db.commit()
    result = await db.execute(
        select(UserPipeline)
        .where(UserPipeline.id == pipeline.id)
        .options(selectinload(UserPipeline.steps))
    )
    return _pipeline_to_response(result.scalar_one())


@router.put("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    pipeline_id: uuid.UUID,
    body: PipelineUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing pipeline (name, description, or steps) for the authenticated user."""
    result = await db.execute(
        select(UserPipeline)
        .where(UserPipeline.id == pipeline_id, UserPipeline.user_id == user.id)
        .options(selectinload(UserPipeline.steps))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if body.name is not None:
        pipeline.name = body.name
    if body.description is not None:
        pipeline.description = body.description

    if body.steps is not None:
        for step in list(pipeline.steps):
            await db.delete(step)
        await db.flush()
        for step_in in body.steps:
            db.add(
                UserPipelineStep(
                    pipeline_id=pipeline.id,
                    step_order=step_in.step_order,
                    tool_id=step_in.tool_id,
                    tool_label=step_in.tool_label,
                    config=step_in.config,
                )
            )

    await db.commit()
    result = await db.execute(
        select(UserPipeline)
        .where(UserPipeline.id == pipeline_id)
        .options(selectinload(UserPipeline.steps))
    )
    return _pipeline_to_response(result.scalar_one())


@router.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(
    pipeline_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a pipeline by marking it inactive (sets is_active=False)."""
    pipeline = await db.get(UserPipeline, pipeline_id)
    if not pipeline or pipeline.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    pipeline.is_active = False
    await db.commit()


# ── Discovered Tools ────────────────────────────────────────────────────────


@router.get("/discovered-tools", response_model=DiscoveredToolsResponse)
async def get_discovered_tools(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Return paginated list of tools the authenticated user has discovered."""
    # Total count (unaffected by pagination)
    count_result = await db.execute(
        select(func.count()).where(UserDiscoveredTool.user_id == user.id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(UserDiscoveredTool)
        .where(UserDiscoveredTool.user_id == user.id)
        .order_by(UserDiscoveredTool.discovered_at.asc())
        .limit(min(limit, 500))
        .offset(offset)
    )
    tools = result.scalars().all()
    return DiscoveredToolsResponse(
        tools=[
            DiscoveredToolItem(
                tool_id=t.tool_id,
                discovered_at=t.discovered_at.isoformat(),
            )
            for t in tools
        ],
        count=total,
    )


# ── Spin History ────────────────────────────────────────────────────────────


@router.get("/spin-history", response_model=SpinHistoryResponse)
async def get_spin_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's most recent 20 spin-wheel entries."""
    result = await db.execute(
        select(UserSpinLog)
        .where(UserSpinLog.user_id == user.id)
        .order_by(UserSpinLog.created_at.desc())
        .limit(20)
    )
    spins = result.scalars().all()
    return SpinHistoryResponse(
        spins=[
            SpinHistoryItem(
                spin_date=s.spin_date.isoformat(),
                reward_type=s.reward_type,
                reward_ref=s.reward_ref,
                iso_week=s.iso_week,
            )
            for s in spins
        ],
    )
