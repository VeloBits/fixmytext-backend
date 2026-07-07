"""Tests for Just-In-Time user provisioning in ``get_current_user``.

JIT provisioning creates a minimal User row the first time a Keycloak-issued
Bearer token is presented for a subject that has no existing DB record. It is
intentionally skipped on the session-cookie path (cookie = echo of DB, never
a source of truth for new users).

Mock target: ``app.core.deps.verify_jwt_raw``
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MOCK_TARGET = "app.core.deps.verify_jwt_raw"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_payload(
    *,
    kc_id: uuid.UUID | None = None,
    email: str = "newuser@example.com",
    email_verified: bool = True,
    preferred_username: str | None = "newuser",
) -> dict:
    payload = {
        "sub": str(kc_id or uuid.uuid4()),
        "email": email,
        "email_verified": email_verified,
    }
    if preferred_username is not None:
        payload["preferred_username"] = preferred_username
    return payload


def _make_user(
    *,
    keycloak_id: uuid.UUID | None = None,
    email: str = "newuser@example.com",
    display_name: str = "newuser",
    is_active: bool = True,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.keycloak_id = keycloak_id or uuid.uuid4()
    user.email = email
    user.display_name = display_name
    user.is_active = is_active
    user.is_email_verified = True
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_time_user_gets_provisioned(async_client):
    """First Bearer request for an unknown Keycloak ID provisions a new user → 200."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    payload = _valid_payload(kc_id=kc_id, email="brand.new@example.com")

    mock_db = AsyncMock()
    # First scalar() call → None (user not found); the JIT path then adds the
    # new user.  A second scalar() call isn't made — the freshly built User
    # object is returned directly from get_current_user.
    mock_db.scalar = AsyncMock(return_value=None)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    # Subscription tier lookup inside /auth/me
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=payload):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer first-time.jwt.token"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["email"] == "brand.new@example.com"
            # Verify add() was called with the new User object
            mock_db.add.assert_called_once()
            added_user = mock_db.add.call_args[0][0]
            assert added_user.email == "brand.new@example.com"
            # Verify flush() was called to write within the transaction
            mock_db.flush.assert_called_once()
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_existing_user_is_not_duplicated(async_client):
    """Bearer request for an existing Keycloak ID skips JIT — no add/flush."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    payload = _valid_payload(kc_id=kc_id)
    existing_user = _make_user(keycloak_id=kc_id, email="existing@example.com")

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=existing_user)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=payload):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer existing-user.jwt.token"},
            )
            assert response.status_code == 200
            # No new user should have been added
            mock_db.add.assert_not_called()
            mock_db.flush.assert_not_called()
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_jit_integrity_error_recovers(async_client):
    """If db.flush() raises IntegrityError (race condition), deps.py catches it,
    rolls back, and re-queries for the already-existing user → 200.

    This tests the IntegrityError recovery path added to ``get_current_user``:
    the first db.scalar() returns None (triggering JIT), flush() raises
    IntegrityError (concurrent insert), and the recovery re-queries → finds the
    user the winning concurrent request just inserted.
    """
    import sqlalchemy.exc

    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    payload = _valid_payload(kc_id=kc_id)

    # The user that the concurrent request inserted (found on re-query).
    recovered_user = _make_user(keycloak_id=kc_id, email=payload["email"])

    mock_db = AsyncMock()
    # First scalar() → None (user not found → JIT path).
    # Second scalar() → recovered_user (found after rollback, during recovery).
    mock_db.scalar = AsyncMock(side_effect=[None, recovered_user])
    mock_db.add = MagicMock()
    # Simulate a race-condition duplicate insert
    mock_db.flush = AsyncMock(
        side_effect=sqlalchemy.exc.IntegrityError("statement", {}, Exception("unique"))
    )
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    mock_db.rollback = AsyncMock()

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=payload):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer race-condition.jwt.token"},
            )
            # Recovery behavior: IntegrityError caught → rollback → re-query → 200
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cookie_auth_does_not_trigger_jit(async_client):
    """Session-cookie with a sub that has no DB row → 401 (not JIT, not 500).

    The JIT path is gated on ``credentials is not None``. A cookie-only request
    has no Bearer credentials, so when the DB lookup returns None the code falls
    into the ``elif user is None`` branch and raises 401.
    """
    import os

    from app.core.session_cookie import build_claims, sign_session

    secret = os.environ.get("SECRET_KEY", "test-secret-key-at-least-32-characters")

    claims = build_claims(
        sub=str(uuid.uuid4()),
        email="cookie@example.com",
        email_verified=True,
        roles=["user"],
        max_age_seconds=3600,
    )
    cookie_value = sign_session(claims, secret)

    from app.db.session import get_db
    from main import app

    mock_db = AsyncMock()
    # User is not in DB — simulates a stale/orphaned cookie
    mock_db.scalar = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def override_get_db():
        yield mock_db

    # No Bearer token in headers — cookie-only path
    app.dependency_overrides[get_db] = override_get_db
    try:
        response = await async_client.get(
            "/api/v1/auth/me",
            cookies={"fixmytext_session": cookie_value},
        )
        # Cookie with unknown sub → 401, NOT a 500 or JIT-provisioned 200
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_jit_sets_email_from_jwt_payload(async_client):
    """The JIT-provisioned user's email comes from the JWT ``email`` claim."""
    from app.db.session import get_db
    from main import app

    kc_id = uuid.uuid4()
    jwt_email = "from.jwt@example.com"
    payload = _valid_payload(kc_id=kc_id, email=jwt_email)

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def override_get_db():
        yield mock_db

    with patch(_MOCK_TARGET, return_value=payload):
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer first-time.jwt.token"},
            )
            assert response.status_code == 200
            mock_db.add.assert_called_once()
            added_user = mock_db.add.call_args[0][0]
            assert added_user.email == jwt_email
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_jit_sets_display_name_from_preferred_username(async_client):
    """JIT uses ``preferred_username`` for display_name; falls back to email."""
    from app.db.session import get_db
    from main import app

    # Case 1: preferred_username present
    kc_id_a = uuid.uuid4()
    payload_a = _valid_payload(
        kc_id=kc_id_a, email="a@example.com", preferred_username="johndoe"
    )

    # Case 2: preferred_username absent
    kc_id_b = uuid.uuid4()
    payload_b = _valid_payload(
        kc_id=kc_id_b, email="b@example.com", preferred_username=None
    )

    mock_db_a = AsyncMock()
    mock_db_a.scalar = AsyncMock(return_value=None)
    mock_db_a.add = MagicMock()
    mock_db_a.flush = AsyncMock()
    mock_db_a.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    mock_db_b = AsyncMock()
    mock_db_b.scalar = AsyncMock(return_value=None)
    mock_db_b.add = MagicMock()
    mock_db_b.flush = AsyncMock()
    mock_db_b.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    # --- Case 1: preferred_username → display_name = "johndoe" ---
    async def override_get_db_a():
        yield mock_db_a

    with patch(_MOCK_TARGET, return_value=payload_a):
        app.dependency_overrides[get_db] = override_get_db_a
        try:
            resp = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer with-username.jwt"},
            )
            assert resp.status_code == 200
            mock_db_a.add.assert_called_once()
            assert mock_db_a.add.call_args[0][0].display_name == "johndoe"
        finally:
            app.dependency_overrides.clear()

    # Clear cookies so Case 1's session cookie doesn't interfere with Case 2.
    async_client.cookies.clear()

    # --- Case 2: no preferred_username → display_name = email ---
    async def override_get_db_b():
        yield mock_db_b

    with patch(_MOCK_TARGET, return_value=payload_b):
        app.dependency_overrides[get_db] = override_get_db_b
        try:
            resp = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer no-username.jwt"},
            )
            assert resp.status_code == 200
            mock_db_b.add.assert_called_once()
            assert mock_db_b.add.call_args[0][0].display_name == "b@example.com"
        finally:
            app.dependency_overrides.clear()
