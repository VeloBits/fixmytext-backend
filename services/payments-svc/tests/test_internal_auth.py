"""Unit tests for the internal-secret guard, visitor-key derivation, and
JIT user-provisioning race-condition recovery in the check_access endpoint.

No database required.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import internal as internal_ep
from app.core import deps


async def test_verify_internal_secret_accepts_match(monkeypatch):
    monkeypatch.setattr(deps.settings, "INTERNAL_SHARED_SECRET", "s3cret")
    assert await deps.verify_internal_secret(x_internal_secret="s3cret") is None


async def test_verify_internal_secret_rejects_wrong(monkeypatch):
    monkeypatch.setattr(deps.settings, "INTERNAL_SHARED_SECRET", "s3cret")
    with pytest.raises(HTTPException) as exc:
        await deps.verify_internal_secret(x_internal_secret="nope")
    assert exc.value.status_code == 401


async def test_verify_internal_secret_fails_closed_when_unset(monkeypatch):
    """An unset secret denies every call so the gate is never silently open."""
    monkeypatch.setattr(deps.settings, "INTERNAL_SHARED_SECRET", "")
    with pytest.raises(HTTPException) as exc:
        await deps.verify_internal_secret(x_internal_secret="")
    assert exc.value.status_code == 401


def test_visitor_key_is_deterministic_and_ip_ua_bound():
    a = internal_ep._visitor_key("1.2.3.4", "UA/1.0")
    b = internal_ep._visitor_key("1.2.3.4", "UA/1.0")
    c = internal_ep._visitor_key("9.9.9.9", "UA/1.0")
    assert a == b  # same IP+UA -> same key
    assert a != c  # different IP -> different key
    assert len(a) == 64  # sha256 hexdigest


# ── JIT provisioning race-condition recovery (H-3) ───────────────────────────


@pytest.mark.asyncio
async def test_check_access_jit_recovers_from_concurrent_insert_race():
    """When two simultaneous first-requests both try to INSERT the same user,
    the second hits IntegrityError.  check_access must re-query and continue
    instead of surfacing a 500 (H-3)."""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    from app.api.v1.endpoints.internal import check_access
    from app.schemas.internal import CheckAccessRequest

    keycloak_id = uuid.uuid4()
    req = CheckAccessRequest(
        tool_id="uppercase",
        tool_type="local",
        principal_type="user",
        user_id=str(keycloak_id),
        email="race@test.test",
        email_verified=True,
    )

    recovered_user = MagicMock()
    recovered_user.id = uuid.uuid4()
    recovered_user.keycloak_id = keycloak_id

    db = AsyncMock()
    # First scalar() → user not found; second scalar() → race winner's row
    db.scalar = AsyncMock(side_effect=[None, recovered_user])
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=SAIntegrityError("", {}, Exception()))
    db.rollback = AsyncMock()
    db.commit = AsyncMock()

    with patch(
        "app.api.v1.endpoints.internal.check_tool_access",
        new_callable=AsyncMock,
        return_value={"allowed": True, "reason": "free"},
    ):
        response = await check_access(req=req, _=None, db=db)

    assert response.allowed is True
    db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_check_access_jit_raises_503_when_race_recovery_finds_nothing():
    """If the re-query after an IntegrityError also returns None the endpoint
    must raise 503 rather than AttributeError or an unhandled exception."""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    from app.api.v1.endpoints.internal import check_access
    from app.schemas.internal import CheckAccessRequest

    keycloak_id = uuid.uuid4()
    req = CheckAccessRequest(
        tool_id="uppercase",
        tool_type="local",
        principal_type="user",
        user_id=str(keycloak_id),
        email=None,
        email_verified=False,
    )

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)  # both lookup and recovery return None
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=SAIntegrityError("", {}, Exception()))
    db.rollback = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await check_access(req=req, _=None, db=db)

    assert exc_info.value.status_code == 503
