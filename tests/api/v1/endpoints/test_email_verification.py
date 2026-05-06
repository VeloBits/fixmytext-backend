"""Tests for /auth/verify-email, /auth/resend-verification, and the
``get_verified_user`` dependency that gates AI endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.db.models import EmailVerificationToken
from app.db.session import get_db
from app.services.auth_service import (
    EMAIL_VERIFICATION_TOKEN_TTL,
    RESEND_VERIFICATION_COOLDOWN,
    _hash_token,
    resend_verification,
    verify_email,
)
from main import app
from tests.conftest import make_mock_db, make_user

# ── Helpers ──────────────────────────────────────────────────────────────────


def _sequenced_execute_db(*results):
    """Mock DB whose successive ``execute()`` calls return the given results."""
    db = make_mock_db()
    mocks = []
    for r in results:
        m = MagicMock()
        m.scalar_one_or_none.return_value = r
        mocks.append(m)
    db.execute.side_effect = mocks
    return db


def _verification_token(
    user_id,
    *,
    ttl: timedelta | None = None,
    used: bool = False,
    created_at: datetime | None = None,
):
    raw = "raw-verification-token-for-testing"
    row = EmailVerificationToken(
        user_id=user_id,
        token_hash=_hash_token(raw),
        expires_at=datetime.now(UTC)
        + (ttl if ttl is not None else EMAIL_VERIFICATION_TOKEN_TTL),
    )
    row.used_at = datetime.now(UTC) if used else None
    row.created_at = created_at or datetime.now(UTC)
    return raw, row


# ── /auth/verify-email ────────────────────────────────────────────────────────


def test_verify_email_valid_flow_marks_user_verified():
    user = make_user(is_email_verified=False)
    raw_token, token_row = _verification_token(user.id)

    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/verify-email", json={"token": raw_token}
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert user.is_email_verified is True
    assert token_row.used_at is not None
    db.commit.assert_awaited()


def test_verify_email_expired_token_returns_400():
    user = make_user(is_email_verified=False)
    raw_token, token_row = _verification_token(user.id, ttl=timedelta(seconds=-1))

    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/verify-email", json={"token": raw_token}
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert user.is_email_verified is False


def test_verify_email_unknown_token_returns_400():
    db = _sequenced_execute_db(None)

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/verify-email", json={"token": "unknown"}
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_verify_email_reused_token_returns_400():
    user = make_user(is_email_verified=True)
    raw_token, token_row = _verification_token(user.id, used=True)

    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/verify-email", json={"token": raw_token}
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_verify_email_missing_token_rejected_by_validation():
    resp = TestClient(app).post("/api/v1/auth/verify-email", json={})
    assert resp.status_code == 422


# ── /auth/resend-verification ─────────────────────────────────────────────────


def test_resend_verification_issues_new_token_when_no_prior(monkeypatch):
    # Pin console mode so the dev-echo assertion stays deterministic across
    # local .env configurations.
    monkeypatch.setattr("app.api.v1.endpoints.auth.settings.EMAIL_BACKEND", "console")
    monkeypatch.setattr("app.api.v1.endpoints.auth.settings.SMTP_HOST", "")

    user = make_user(is_email_verified=False)
    db = _sequenced_execute_db(None)  # no prior token exists

    async def _get_db():
        yield db

    async def _user_dep():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _user_dep

    access = create_access_token(user.id)
    with patch(
        "app.api.v1.endpoints.auth.send_verification_email", new_callable=AsyncMock
    ) as mock_send:
        resp = TestClient(app, raise_server_exceptions=True).post(
            "/api/v1/auth/resend-verification",
            headers={"Authorization": f"Bearer {access}"},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_token"]  # console-mode dev echo
    db.add.assert_called_once()
    # The verification email flow must be invoked with the issued token.
    assert mock_send.await_count == 1
    sent_user, sent_token = mock_send.await_args.args
    assert sent_user.id == user.id
    assert sent_token == data["verification_token"]


def test_resend_verification_respects_cooldown_returns_429():
    user = make_user(is_email_verified=False)
    # Previous token issued 30s ago — well inside the 2-minute cooldown.
    _, prior = _verification_token(
        user.id, created_at=datetime.now(UTC) - timedelta(seconds=30)
    )
    db = _sequenced_execute_db(prior)

    async def _get_db():
        yield db

    async def _user_dep():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _user_dep

    access = create_access_token(user.id)
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/resend-verification",
        headers={"Authorization": f"Bearer {access}"},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    db.add.assert_not_called()


def test_resend_verification_allows_after_cooldown_elapsed():
    user = make_user(is_email_verified=False)
    # Previous token issued longer ago than the cooldown.
    old = datetime.now(UTC) - RESEND_VERIFICATION_COOLDOWN - timedelta(seconds=5)
    _, prior = _verification_token(user.id, created_at=old)
    db = _sequenced_execute_db(prior)

    async def _get_db():
        yield db

    async def _user_dep():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _user_dep

    access = create_access_token(user.id)
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/resend-verification",
        headers={"Authorization": f"Bearer {access}"},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    db.add.assert_called_once()


def test_resend_verification_noop_for_already_verified_user():
    user = make_user(is_email_verified=True)
    db = make_mock_db()

    async def _get_db():
        yield db

    async def _user_dep():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _user_dep

    access = create_access_token(user.id)
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/resend-verification",
        headers={"Authorization": f"Bearer {access}"},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    # Endpoint returns the same opaque response shape, but no token is issued
    # (and no token is echoed back) for an already-verified account.
    assert resp.json()["verification_token"] is None
    db.add.assert_not_called()


def test_resend_verification_requires_auth():
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/resend-verification"
    )
    assert resp.status_code == 401


# ── Verification gate on tool endpoints ─────────────────────────────────────


def _post_tool(path: str, user, body: dict):
    """Helper: POST *body* to *path* as the given user (or visitor if None)."""
    from app.core.deps import get_optional_user

    async def _user_dep():
        return user

    async def _get_db():
        yield make_mock_db()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _user_dep
    app.dependency_overrides[get_optional_user] = _user_dep

    headers = {}
    if user is not None:
        headers["Authorization"] = f"Bearer {create_access_token(user.id)}"

    try:
        return TestClient(app, raise_server_exceptions=False).post(
            path, json=body, headers=headers
        )
    finally:
        app.dependency_overrides.clear()


def test_ai_endpoint_blocks_unverified_user():
    """AI tools return 403 ``email_not_verified`` for unverified users."""
    unverified = make_user(is_email_verified=False)
    resp = _post_tool(
        "/api/v1/text/translate",
        unverified,
        {"text": "hi", "target_language": "french"},
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert isinstance(detail, dict) and detail.get("code") == "email_not_verified"


def test_local_tool_also_blocks_unverified_user():
    """Local (non-AI) tools must also gate on email verification for authed
    users — fresh signups shouldn't get to use the app until we've confirmed
    they own the inbox they registered with."""
    unverified = make_user(is_email_verified=False)
    resp = _post_tool("/api/v1/text/uppercase", unverified, {"text": "hello"})
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert isinstance(detail, dict) and detail.get("code") == "email_not_verified"


def test_local_tool_allows_visitors():
    """Anonymous visitors still get free-tier access — only authed-but-
    unverified users are blocked."""
    resp = _post_tool("/api/v1/text/uppercase", None, {"text": "hello"})
    # Visitor may succeed or hit quota (429); the point is it must not be 403.
    assert resp.status_code != 403


# ── Service layer unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_email_service_happy_path():
    user = make_user(is_email_verified=False)
    raw_token, token_row = _verification_token(user.id)
    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    updated = await verify_email(db, raw_token)
    assert updated.is_email_verified is True
    assert token_row.used_at is not None


@pytest.mark.asyncio
async def test_verify_email_service_expired_raises_400():
    from fastapi import HTTPException

    user = make_user(is_email_verified=False)
    raw_token, token_row = _verification_token(user.id, ttl=timedelta(seconds=-1))
    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc_info:
        await verify_email(db, raw_token)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_resend_verification_service_already_verified_returns_none():
    user = make_user(is_email_verified=True)
    db = make_mock_db()
    result = await resend_verification(db, user)
    assert result is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_resend_verification_service_cooldown_raises_429():
    from fastapi import HTTPException

    user = make_user(is_email_verified=False)
    _, prior = _verification_token(
        user.id, created_at=datetime.now(UTC) - timedelta(seconds=10)
    )
    db = _sequenced_execute_db(prior)

    with pytest.raises(HTTPException) as exc_info:
        await resend_verification(db, user)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in (exc_info.value.headers or {})
