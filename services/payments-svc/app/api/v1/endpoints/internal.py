"""Internal service-to-service endpoints.

``POST /internal/v1/check-access`` restores the per-tool entitlement gate that
the strangler-fig extraction dropped (H-1). text-svc and ai-svc call it before
running a tool; payments-svc remains the single owner of billing state and the
single place where the atomic credit/pass decrement happens (BE-DATA-01/02).

Not exposed through the public gateway and guarded by ``verify_internal_secret``.
"""

import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import verify_internal_secret
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.internal import CheckAccessRequest, CheckAccessResponse
from app.services.pass_service import check_tool_access, check_visitor_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/v1", tags=["Internal"])


def _visitor_key(ip_address: str | None, user_agent: str | None) -> str:
    """Derive a stable, server-side visitor identity from IP + User-Agent.

    Replaces the client-supplied fingerprint as the quota key (BE-PAY-10) so a
    visitor cannot reset their free-use counter by rotating X-Visitor-Id.
    """
    raw = f"{ip_address or ''}|{user_agent or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/check-access", response_model=CheckAccessResponse)
async def check_access(
    req: CheckAccessRequest,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db),
) -> CheckAccessResponse:
    """Check (and consume) a tool entitlement for a user or anonymous visitor.

    Returns 200 with ``allowed=false`` for quota-exhausted (the caller decides
    UX), 422 for malformed input, 401 for a bad internal secret, and 503 if the
    database is unavailable (callers fail closed for paid tools on 503).
    """
    try:
        if req.principal_type == "user":
            if not req.user_id:
                raise HTTPException(422, "user_id required for principal_type=user")
            try:
                keycloak_id = uuid.UUID(req.user_id)
            except (ValueError, TypeError) as exc:
                raise HTTPException(422, "invalid user_id") from exc

            user = await db.scalar(select(User).where(User.keycloak_id == keycloak_id))
            if user is None:
                # JIT provisioning — mirror deps.get_current_user so first-time
                # users are tracked. Placeholder email keeps the UNIQUE intact.
                # IntegrityError handling covers the race where two simultaneous
                # first-requests both attempt to insert the same keycloak_id.
                user = User(
                    keycloak_id=keycloak_id,
                    email=req.email or f"{keycloak_id}@users.noreply",
                    display_name=req.email or str(keycloak_id),
                    is_email_verified=req.email_verified,
                )
                db.add(user)
                try:
                    await db.flush()
                except IntegrityError as exc:
                    await db.rollback()
                    user = await db.scalar(
                        select(User).where(User.keycloak_id == keycloak_id)
                    )
                    if user is None:
                        raise HTTPException(
                            503, "entitlement service unavailable"
                        ) from exc

            result = await check_tool_access(
                user, req.tool_id, req.tool_type, db, auto_commit=False
            )

        elif req.principal_type == "visitor":
            visitor_key = _visitor_key(req.ip_address, req.user_agent)
            result = await check_visitor_access(
                visitor_key,
                req.ip_address or "",
                req.tool_id,
                req.tool_type,
                db,
                auto_commit=False,
            )
        else:
            raise HTTPException(422, "invalid principal_type")

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("check-access DB error for tool=%s", req.tool_id)
        raise HTTPException(503, "entitlement service unavailable") from exc

    return CheckAccessResponse(
        allowed=result.get("allowed", False),
        reason=result.get("reason", "blocked"),
        message=result.get("message"),
        uses_today=result.get("uses_today"),
        max_free=result.get("max_free"),
        credits_remaining=result.get("credits_remaining"),
    )
