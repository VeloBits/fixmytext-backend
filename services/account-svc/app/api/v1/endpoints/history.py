"""Operation history endpoints -- persistent per-user operation tracking.

Provides CRUD for the user's operation history including paginated listing,
recording new operations, per-tool stats, and soft-delete for both individual
entries and bulk clear.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models import OperationHistory, User
from app.db.session import get_db
from app.schemas.history import (
    HistoryCreate,
    HistoryListResponse,
    HistoryResponse,
    HistoryStatsResponse,
)

router = APIRouter(prefix="/history", tags=["History"])

# Use the centralized config value so operators can tune truncation without
# a code change; falls back to 500 if the setting is absent.
PREVIEW_MAX = getattr(settings, "HISTORY_PREVIEW_MAX_LENGTH", 500)


def _row_to_response(row: OperationHistory) -> HistoryResponse:
    """Convert an OperationHistory ORM instance to its API response schema."""
    return HistoryResponse(
        id=str(row.id),
        tool_id=row.tool_id,
        tool_label=row.tool_label,
        tool_type=row.tool_type,
        input_preview=row.input_preview,
        output_preview=row.output_preview,
        input_length=row.input_length,
        output_length=row.output_length,
        status=row.status,
        created_at=row.created_at.isoformat(),
    )


# ── List (paginated, newest first) ──────────────────────────────────────────


@router.get("", response_model=HistoryListResponse)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    tool_id: str | None = Query(None, max_length=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of the user's operation history (newest first).

    Soft-deleted entries are excluded.  Optionally filter by ``tool_id``.
    """
    # Exclude soft-deleted rows from both the data query and the count query
    base = select(OperationHistory).where(
        OperationHistory.user_id == user.id,
        OperationHistory.is_deleted == False,  # noqa: E712
    )
    count_base = (
        select(func.count())
        .select_from(OperationHistory)
        .where(
            OperationHistory.user_id == user.id,
            OperationHistory.is_deleted == False,  # noqa: E712
        )
    )

    if tool_id:
        base = base.where(OperationHistory.tool_id == tool_id)
        count_base = count_base.where(OperationHistory.tool_id == tool_id)

    total = (await db.execute(count_base)).scalar() or 0

    rows = (
        (
            await db.execute(
                base.order_by(desc(OperationHistory.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return HistoryListResponse(
        items=[_row_to_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


# ── Record a new operation ──────────────────────────────────────────────────


@router.post("", response_model=HistoryResponse, status_code=201)
async def record_operation(
    body: HistoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a new text-transformation operation in the user's history.

    Input and output previews are truncated to ``PREVIEW_MAX`` characters to
    avoid bloating the history table.
    """
    row = OperationHistory(
        user_id=user.id,
        tool_id=body.tool_id,
        tool_label=body.tool_label,
        tool_type=body.tool_type,
        input_preview=body.input_preview[:PREVIEW_MAX],
        output_preview=body.output_preview[:PREVIEW_MAX],
        input_length=body.input_length,
        output_length=body.output_length,
        status=body.status,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _row_to_response(row)


# ── Stats (must come before /{entry_id} to avoid path conflict) ─────────────


@router.get("/stats/summary", response_model=HistoryStatsResponse)
async def get_history_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a summary of the user's operation history.

    Uses a single grouped query that fetches per-tool count **and**
    last-used timestamp in one database round-trip.  The ``recent_tools``
    list is derived from the same result set by sorting on ``last_used``
    instead of issuing a separate query.  Soft-deleted entries are excluded.
    """
    # Combined query: per-tool count + last-used timestamp in one round-trip
    all_stats = (
        await db.execute(
            select(
                OperationHistory.tool_id,
                func.count().label("count"),
                func.max(OperationHistory.created_at).label("last_used"),
            )
            .where(
                OperationHistory.user_id == user.id,
                OperationHistory.is_deleted == False,  # noqa: E712
            )
            .group_by(OperationHistory.tool_id)
            .order_by(func.count().desc())
        )
    ).all()

    # Total is the sum of per-tool counts
    total = sum(row.count for row in all_stats)

    # Breakdown keyed by tool_id
    tools_breakdown = {row.tool_id: row.count for row in all_stats}

    # Derive recent tools from the same data by sorting on last_used
    recent_tool_ids = sorted(all_stats, key=lambda r: r.last_used, reverse=True)
    recent_tools = list(dict.fromkeys(r.tool_id for r in recent_tool_ids))[:10]

    return HistoryStatsResponse(
        total_operations=total,
        tools_breakdown=tools_breakdown,
        recent_tools=recent_tools,
    )


# ── Clear all history ────────────────────────────────────────────────────────


@router.delete("", status_code=204)
async def clear_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete all history entries for the authenticated user.

    Sets ``is_deleted=True`` on every non-deleted row rather than physically
    removing data, preserving audit trail and enabling future undo.
    """
    await db.execute(
        update(OperationHistory)
        .where(
            OperationHistory.user_id == user.id,
            OperationHistory.is_deleted == False,  # noqa: E712
        )
        .values(is_deleted=True)
    )
    await db.commit()


# ── Get single entry ────────────────────────────────────────────────────────


@router.get("/{entry_id}", response_model=HistoryResponse)
async def get_history_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single history entry by ID for the authenticated user.

    Returns 404 if the entry does not exist, belongs to another user, or
    has been soft-deleted.
    """
    row = await db.get(OperationHistory, entry_id)
    if not row or row.user_id != user.id or row.is_deleted:
        raise HTTPException(status_code=404, detail="History entry not found")
    return _row_to_response(row)


# ── Delete single entry ─────────────────────────────────────────────────────


@router.delete("/{entry_id}", status_code=204)
async def delete_history_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a single history entry for the authenticated user.

    Marks the row as deleted rather than physically removing it, consistent
    with the bulk ``clear_history`` endpoint.
    """
    row = await db.get(OperationHistory, entry_id)
    if not row or row.user_id != user.id or row.is_deleted:
        raise HTTPException(status_code=404, detail="History entry not found")
    row.is_deleted = True
    await db.commit()
