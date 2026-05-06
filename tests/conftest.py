"""
Shared test fixtures for the FixMyText backend test suite.

Uses mocked DB sessions and dependency overrides — no real PostgreSQL required.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_current_user, get_optional_user
from app.core.rate_limit import (
    ai_limiter,
    auth_limiter,
    forgot_password_limiter,
    verification_resend_limiter,
)
from app.core.security import hash_password
from app.db.models import User
from app.db.session import get_db
from main import app

# ── Autouse: reset shared rate limiter state between tests ───────────────────


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Clear in-memory rate-limiter state so tests don't trip each other's limits."""
    for limiter in (
        auth_limiter,
        ai_limiter,
        forgot_password_limiter,
        verification_resend_limiter,
    ):
        hits = getattr(limiter, "_hits", None)
        if hits is not None:
            hits.clear()
    yield


# ── User factory ─────────────────────────────────────────────────────────────


def make_user(**kwargs) -> User:
    """Create a detached User instance (no DB session required)."""
    user = User(
        email=kwargs.get("email", "test@example.com"),
        hashed_password=kwargs.get("hashed_password", hash_password("password123")),
        display_name=kwargs.get("display_name", "Test User"),
    )
    # Explicitly set all fields — SQLAlchemy defaults only apply on DB flush/insert
    user.id = kwargs.get("id", uuid.uuid4())
    user.is_active = kwargs.get("is_active", True)
    user.is_email_verified = kwargs.get("is_email_verified", True)
    user.region = kwargs.get("region", "US")
    user.referral_code = kwargs.get("referral_code")
    user.referred_by = kwargs.get("referred_by")
    # Set server_default fields manually (won't be set without a DB flush)
    user.created_at = kwargs.get("created_at", datetime.now(UTC))
    user.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    user.last_login_at = None
    return user


# ── DB mock factory ───────────────────────────────────────────────────────────


def make_mock_db() -> AsyncMock:
    """Return an AsyncMock SQLAlchemy session with sensible defaults."""
    db = AsyncMock()

    # execute() returns a result that supports common chaining
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.all.return_value = []
    db.execute.return_value = result

    # db.get(Model, pk) returns None by default
    db.get.return_value = None

    # db.add() is synchronous in SQLAlchemy (not awaited); db.delete() is awaited
    db.add = MagicMock()

    # db.refresh(obj) — populate server_default fields (UUID, timestamps)
    async def _smart_refresh(obj):
        # Ensure primary key UUID is set
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        if not getattr(obj, "created_at", None):
            obj.created_at = datetime.now(UTC)
        if not getattr(obj, "updated_at", None):
            obj.updated_at = datetime.now(UTC)

    db.refresh.side_effect = _smart_refresh

    return db


# ── Pytest fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def fake_user() -> User:
    """A detached User instance for use in tests."""
    return make_user()


@pytest.fixture
def mock_db() -> AsyncMock:
    """A mocked async SQLAlchemy session."""
    return make_mock_db()


@pytest.fixture
def client(fake_user, mock_db):
    """
    Authenticated TestClient: get_current_user → fake_user,
    get_optional_user → fake_user.
    """

    async def _get_db():
        yield mock_db

    async def _get_current_user():
        return fake_user

    async def _get_optional_user():
        return fake_user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    app.dependency_overrides[get_optional_user] = _get_optional_user

    yield TestClient(app, raise_server_exceptions=True)

    app.dependency_overrides.clear()


@pytest.fixture
def anon_client(mock_db):
    """
    Anonymous TestClient: get_optional_user → None (no auth),
    get_current_user not overridden (will 401 if used by the endpoint).
    """

    async def _get_db():
        yield mock_db

    async def _get_optional_user():
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_optional_user] = _get_optional_user

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client(mock_db):
    """TestClient where get_current_user is NOT overridden — requests will 401."""

    async def _get_db():
        yield mock_db

    async def _get_optional_user():
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_optional_user] = _get_optional_user

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()
