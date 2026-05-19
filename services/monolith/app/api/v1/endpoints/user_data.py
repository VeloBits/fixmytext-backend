"""User data endpoints: preferences, gamification, templates, ui-settings, favorites, tool-stats, pipelines.

Covers all per-user data CRUD operations including paginated listing of
templates and pipelines, favorite management, gamification state, and UI
preferences.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.db.models import (
    User,
    UserDiscoveredTool,
    UserFavoriteTool,
    UserGamification,
    UserPipeline,
    UserPipelineStep,
    UserPreferences,
    UserSpinLog,
    UserTemplate,
    UserToolStats,
    UserUiSettings,
)
from app.db.session import get_db
from app.schemas.user_data import (
    DiscoveredToolItem,
    DiscoveredToolsResponse,
    FavoritesResponse,
    FavoriteToolItem,
    GamificationResponse,
    GamificationUpdate,
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
    ToolStatItem,
    ToolStatsResponse,
    UiSettingsResponse,
    UiSettingsUpdate,
)

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


# ── Gamification ─────────────────────────────────────────────────────────────


async def _gam_to_response(
    gam: UserGamification, db: AsyncSession
) -> GamificationResponse:
    """Convert ORM model to response schema — reads from normalized tables."""
    # Date columns: use new Date columns, format as ISO string
    streak_last_date = (
        gam.streak_last_date.isoformat() if gam.streak_last_date else None
    )
    daily_quest_date = (
        gam.daily_quest_date.isoformat() if gam.daily_quest_date else None
    )

    return GamificationResponse(
        xp=gam.xp,
        streak_current=gam.streak_current,
        streak_last_date=streak_last_date,
        total_ops=gam.total_ops,
        total_chars=gam.total_chars,
        achievements=gam.achievements,
        completed_quests=gam.completed_quests,
        daily_quest_id=gam.daily_quest_id,
        daily_quest_date=daily_quest_date,
        daily_quest_completed=gam.daily_quest_completed,
    )


@router.get("/gamification", response_model=GamificationResponse)
async def get_gamification(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's gamification state (XP, streak, quests)."""
    gam = await db.get(UserGamification, user.id)
    if not gam:
        return GamificationResponse()
    return await _gam_to_response(gam, db)


@router.put("/gamification", response_model=GamificationResponse)
async def update_gamification(
    body: GamificationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's gamification state (partial update)."""
    gam = await db.get(UserGamification, user.id)
    if not gam:
        gam = UserGamification(user_id=user.id)
        db.add(gam)

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "streak_last_date" and value:
            gam.streak_last_date = date.fromisoformat(value)
        elif key == "daily_quest_date" and value:
            gam.daily_quest_date = date.fromisoformat(value)
        elif key not in ("streak_last_date", "daily_quest_date"):
            setattr(gam, key, value)

    await db.commit()
    await db.refresh(gam)
    return await _gam_to_response(gam, db)


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
        .where(UserTemplate.user_id == user.id)
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
        user_id=user.id, name=body.name, text=body.text, tool_id=body.tool_id
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
        return {"tool_id": tool_id, "sort_order": existing.sort_order}

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
    limit: int = 200,
    offset: int = 0,
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
