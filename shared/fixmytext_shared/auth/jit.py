"""Just-in-Time user provisioning helper.

When a Keycloak-authenticated user hits a service for the first time, their
Keycloak subject UUID may not yet have a matching row in auth.users.
This module handles creating that row atomically, including recovery from
the IntegrityError race condition where two simultaneous first-requests
both attempt to insert.
"""

import logging
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def jit_provision_user[T](
    db: AsyncSession,
    user_class: type[T],
    keycloak_id: uuid.UUID,
    payload: dict[str, Any],
) -> T:
    """Create a minimal User row for a first-time Bearer JWT holder.

    Accepts the service-specific *user_class* ORM model (account-svc and
    payments-svc each create their own via ``make_user_class``).

    Handles the IntegrityError race condition where two simultaneous
    first-requests both attempt to insert — the second request rolls back and
    re-queries for the row the first request committed.

    Returns the newly created or race-recovered User.
    Raises ``HTTPException(401)`` if race recovery fails.
    """
    email = payload.get("email", "").strip()
    if not email:
        logger.warning(
            "auth: JIT rejected — no email claim in JWT for keycloak_id=%s", keycloak_id
        )
        raise HTTPException(status_code=401, detail="Not authenticated")
    logger.info("auth: JIT provisioning user keycloak_id=%s", keycloak_id)
    user = user_class(
        keycloak_id=keycloak_id,
        email=email,
        display_name=payload.get("preferred_username") or email or "User",
        hashed_password=None,
        is_email_verified=bool(payload.get("email_verified", False)),
    )
    try:
        db.add(user)
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "auth: JIT race condition for keycloak_id=%s, recovering", keycloak_id
        )
        user = await db.scalar(
            select(user_class).where(user_class.keycloak_id == keycloak_id)
        )
        if user is None or user.keycloak_id != keycloak_id:
            raise HTTPException(status_code=401, detail="Not authenticated") from exc
    return user
