"""Tests for the password reset flow: /auth/forgot-password and /auth/reset-password."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_password, verify_password
from app.db.models import PasswordResetToken
from app.db.session import get_db
from app.services.auth_service import (
    PASSWORD_RESET_TOKEN_TTL,
    _hash_token,
    create_password_reset_token,
    reset_password,
)
from main import app
from tests.conftest import make_mock_db, make_user

# ── Helpers ──────────────────────────────────────────────────────────────────


def _user_lookup_db(user):
    """Mock DB where db.execute(select(User)...) returns ``user``."""
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result
    return db


def _sequenced_execute_db(*results):
    """Mock DB whose successive db.execute() calls return the given results."""
    db = make_mock_db()
    mocks = []
    for r in results:
        m = MagicMock()
        m.scalar_one_or_none.return_value = r
        mocks.append(m)
    db.execute.side_effect = mocks
    return db


def _token_row(user_id, *, ttl: timedelta | None = None, used: bool = False):
    raw = "raw-reset-token-for-testing"
    row = PasswordResetToken(
        user_id=user_id,
        token_hash=_hash_token(raw),
        expires_at=datetime.now(UTC)
        + (ttl if ttl is not None else PASSWORD_RESET_TOKEN_TTL),
    )
    row.used_at = datetime.now(UTC) if used else None
    row.created_at = datetime.now(UTC)
    return raw, row


# ── /auth/forgot-password ─────────────────────────────────────────────────────


def test_forgot_password_known_email_sends_email_and_echoes_token_in_console_mode(
    monkeypatch,
):
    # Pin the email backend explicitly so this test stays deterministic across
    # local .env files (a dev with SMTP_HOST set would otherwise flip the
    # response to SMTP-mode and the token echo would be suppressed).
    monkeypatch.setattr("app.api.v1.endpoints.auth.settings.EMAIL_BACKEND", "console")
    monkeypatch.setattr("app.api.v1.endpoints.auth.settings.SMTP_HOST", "")

    user = make_user(email="known@example.com")
    db = _user_lookup_db(user)

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    with patch(
        "app.api.v1.endpoints.auth.send_password_reset_email", new_callable=AsyncMock
    ) as mock_send:
        resp = TestClient(app, raise_server_exceptions=True).post(
            "/api/v1/auth/forgot-password", json={"email": "known@example.com"}
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert "detail" in data
    # Console backend is default in tests — token is echoed back.
    assert data["reset_token"]
    db.add.assert_called_once()
    db.commit.assert_awaited()
    # The email flow must be invoked with the user + the raw token that
    # matches what was hashed into the DB.
    assert mock_send.await_count == 1
    sent_user, sent_token = mock_send.await_args.args
    assert sent_user.id == user.id
    assert sent_token == data["reset_token"]


def test_forgot_password_unknown_email_same_response_shape():
    """Email enumeration protection: unknown email → identical outer response,
    no token persisted, **no email sent**."""
    db = _user_lookup_db(None)

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    with patch(
        "app.api.v1.endpoints.auth.send_password_reset_email", new_callable=AsyncMock
    ) as mock_send:
        resp = TestClient(app, raise_server_exceptions=True).post(
            "/api/v1/auth/forgot-password", json={"email": "ghost@example.com"}
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert "detail" in data
    # No token persisted for unknown emails
    db.add.assert_not_called()
    # Critically: no email sent, so an attacker can't infer registration
    # status from mail-server side-effects either.
    mock_send.assert_not_awaited()


def test_forgot_password_inactive_user_no_token_issued():
    inactive = make_user(email="inactive@example.com", is_active=False)
    db = _user_lookup_db(inactive)

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/forgot-password", json={"email": "inactive@example.com"}
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["reset_token"] is None
    db.add.assert_not_called()


def test_forgot_password_smtp_mode_does_not_echo_token(monkeypatch):
    """When SMTP is configured, the raw reset token must not be echoed in the
    API response — the user retrieves it from the inbox instead."""
    user = make_user(email="known@example.com")
    db = _user_lookup_db(user)

    async def _get_db():
        yield db

    monkeypatch.setattr("app.api.v1.endpoints.auth.settings.EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.settings.SMTP_HOST", "sandbox.smtp.mailtrap.io"
    )

    app.dependency_overrides[get_db] = _get_db
    with patch(
        "app.api.v1.endpoints.auth.send_password_reset_email", new_callable=AsyncMock
    ) as mock_send:
        resp = TestClient(app, raise_server_exceptions=True).post(
            "/api/v1/auth/forgot-password", json={"email": "known@example.com"}
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["reset_token"] is None  # suppressed
    mock_send.assert_awaited_once()


def test_forgot_password_invalid_email_format():
    db = make_mock_db()

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/forgot-password", json={"email": "not-an-email"}
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_forgot_password_rate_limited_after_three_requests(monkeypatch):
    """4th request within the window is rejected with 429.

    The deployed limiter may be a RedisRateLimiter whose check() no-ops when
    Redis is unavailable in the test environment. Swap in a fresh in-memory
    limiter so we exercise the actual 3/min enforcement.
    """
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
    monkeypatch.setattr("app.api.v1.endpoints.auth.forgot_password_limiter", limiter)
    db = _user_lookup_db(None)  # unknown email — cheapest path

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app, raise_server_exceptions=False)
    payload = {"email": "spam@example.com"}

    for _ in range(3):
        ok = client.post("/api/v1/auth/forgot-password", json=payload)
        assert ok.status_code == 200

    blocked = client.post("/api/v1/auth/forgot-password", json=payload)
    app.dependency_overrides.clear()
    assert blocked.status_code == 429


# ── /auth/reset-password (endpoint) ───────────────────────────────────────────


def test_reset_password_valid_flow_changes_password():
    user = make_user(hashed_password=hash_password("old-password"))
    raw_token, token_row = _token_row(user.id)

    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-pw"},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert verify_password("brand-new-pw", user.hashed_password)
    assert token_row.used_at is not None
    db.commit.assert_awaited()


def test_reset_password_expired_token_rejected():
    user = make_user()
    raw_token, token_row = _token_row(user.id, ttl=timedelta(seconds=-1))

    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-pw"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_reset_password_unknown_token_rejected():
    db = _sequenced_execute_db(None)

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "brand-new-pw"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_reset_password_already_used_token_rejected():
    user = make_user()
    raw_token, token_row = _token_row(user.id, used=True)

    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-pw"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_reset_password_short_password_rejected():
    db = make_mock_db()

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/reset-password",
        json={"token": "whatever", "new_password": "short"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


# ── Service layer unit tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_password_reset_token_persists_hashed_token():
    user = make_user(email="svc@example.com")
    db = _user_lookup_db(user)

    issued = await create_password_reset_token(db, "svc@example.com")
    assert issued is not None
    returned_user, raw = issued
    assert returned_user.id == user.id

    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert isinstance(added, PasswordResetToken)
    assert added.token_hash == _hash_token(raw)
    assert added.token_hash != raw  # raw token never stored directly
    assert added.user_id == user.id
    assert added.expires_at > datetime.now(UTC)
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_password_reset_token_returns_none_for_unknown_email():
    db = _user_lookup_db(None)
    issued = await create_password_reset_token(db, "nobody@example.com")
    assert issued is None
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_password_reset_token_returns_none_for_inactive_user():
    inactive = make_user(is_active=False)
    db = _user_lookup_db(inactive)
    issued = await create_password_reset_token(db, inactive.email)
    assert issued is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_reset_password_service_invalidates_token():
    user = make_user(hashed_password=hash_password("old"))
    raw_token, token_row = _token_row(user.id)
    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    updated = await reset_password(db, raw_token, "new-pw-123")
    assert updated.id == user.id
    assert verify_password("new-pw-123", user.hashed_password)
    assert token_row.used_at is not None


@pytest.mark.asyncio
async def test_reset_password_service_expired_raises_400():
    from fastapi import HTTPException

    user = make_user()
    raw_token, token_row = _token_row(user.id, ttl=timedelta(seconds=-1))
    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc_info:
        await reset_password(db, raw_token, "new-pw-123")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_service_unknown_token_raises_400():
    from fastapi import HTTPException

    db = _sequenced_execute_db(None)
    with pytest.raises(HTTPException) as exc_info:
        await reset_password(db, "bogus", "new-pw-123")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_service_already_used_raises_400():
    from fastapi import HTTPException

    user = make_user()
    raw_token, token_row = _token_row(user.id, used=True)
    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc_info:
        await reset_password(db, raw_token, "new-pw-123")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_service_inactive_user_raises_400():
    from fastapi import HTTPException

    user = make_user(is_active=False)
    raw_token, token_row = _token_row(user.id)
    db = _sequenced_execute_db(token_row)
    db.get.return_value = user

    with pytest.raises(HTTPException) as exc_info:
        await reset_password(db, raw_token, "new-pw-123")
    assert exc_info.value.status_code == 400
