"""Tests for the JWT-based password reset flow.

* /auth/forgot-password issues a signed JWT (via
  ``app.core.transactional_tokens.issue_password_reset_token``).
* /auth/reset-password decodes the JWT, verifies its purpose + the embedded
  bcrypt-hash prefix matches the user's current ``hashed_password``, and
  swaps the password. There is **no** DB token table — single-use semantics
  come from the bcrypt-prefix claim being invalidated by any password change.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_password, verify_password
from app.core.transactional_tokens import (
    InvalidTransactionalToken,
    issue_password_reset_token,
    verify_password_reset_token,
)
from app.db.session import get_db
from app.services.auth_service import (
    create_password_reset_token,
    reset_password,
)
from main import app
from tests.conftest import make_mock_db, make_user

# ── Helpers ──────────────────────────────────────────────────────────────────


def _user_lookup_db(user):
    """Mock DB where ``db.execute(select(User)...)`` returns ``user``."""
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result
    return db


# ── /auth/forgot-password ─────────────────────────────────────────────────────


def test_forgot_password_known_email_sends_email_and_echoes_token_in_console_mode(
    monkeypatch,
):
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
    # Console backend → token echoed back. JWT format: header.payload.signature
    echoed = data["reset_token"]
    assert echoed and echoed.count(".") == 2
    # The email flow must be invoked with the same JWT that was echoed.
    assert mock_send.await_count == 1
    sent_user, sent_token = mock_send.await_args.args
    assert sent_user.id == user.id
    assert sent_token == echoed


def test_forgot_password_unknown_email_same_response_shape():
    """Email enumeration protection: unknown email → identical outer response,
    no token issued, **no email sent**."""
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
    assert "detail" in resp.json()
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


def test_forgot_password_smtp_mode_does_not_echo_token(monkeypatch):
    """When SMTP is configured, the raw reset JWT must not be echoed in the
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
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
    monkeypatch.setattr("app.api.v1.endpoints.auth.forgot_password_limiter", limiter)
    db = _user_lookup_db(None)

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


# ── /auth/reset-password ──────────────────────────────────────────────────────


def test_reset_password_valid_flow_changes_password():
    user = make_user(hashed_password=hash_password("old-password"))
    raw_jwt = issue_password_reset_token(user.id, user.hashed_password)

    db = make_mock_db()
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/reset-password",
        json={"token": raw_jwt, "new_password": "brand-new-pw"},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    # The user's stored hash should now verify the new password.
    assert verify_password("brand-new-pw", user.hashed_password)
    db.commit.assert_awaited()


def test_reset_password_token_already_used_is_rejected():
    """After the password is changed, the original JWT must no longer
    decode — it carried a prefix of the *old* bcrypt hash."""
    user = make_user(hashed_password=hash_password("old"))
    raw_jwt = issue_password_reset_token(user.id, user.hashed_password)

    # Simulate that the password was already changed.
    user.hashed_password = hash_password("intervening-change")

    db = make_mock_db()
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/reset-password",
        json={"token": raw_jwt, "new_password": "another-new"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_reset_password_unknown_or_malformed_token_rejected():
    db = make_mock_db()

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/reset-password",
        json={"token": "totally.bogus.token", "new_password": "brand-new-pw"},
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
async def test_create_password_reset_token_issues_jwt():
    user = make_user(email="svc@example.com")
    db = _user_lookup_db(user)

    issued = await create_password_reset_token(db, "svc@example.com")
    assert issued is not None
    returned_user, raw_jwt = issued
    assert returned_user.id == user.id
    assert raw_jwt.count(".") == 2  # JWT shape

    # The JWT must validate against the user's current bcrypt hash.
    sub = verify_password_reset_token(raw_jwt, user.hashed_password)
    assert sub == str(user.id)


@pytest.mark.asyncio
async def test_create_password_reset_token_returns_none_for_unknown_email():
    db = _user_lookup_db(None)
    issued = await create_password_reset_token(db, "nobody@example.com")
    assert issued is None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_password_reset_token_returns_none_for_inactive_user():
    inactive = make_user(is_active=False)
    db = _user_lookup_db(inactive)
    issued = await create_password_reset_token(db, inactive.email)
    assert issued is None


@pytest.mark.asyncio
async def test_reset_password_service_invalidates_after_use():
    """Once the password is changed via reset_password, the same JWT must
    no longer validate (because the bcrypt prefix in the JWT no longer
    matches the user's new hashed_password)."""
    user = make_user(hashed_password=hash_password("old"))
    raw_jwt = issue_password_reset_token(user.id, user.hashed_password)

    db = make_mock_db()
    db.get.return_value = user
    updated = await reset_password(db, raw_jwt, "new-pw-123")
    assert updated.id == user.id
    # Replay should fail.
    with pytest.raises(InvalidTransactionalToken):
        verify_password_reset_token(raw_jwt, user.hashed_password)


@pytest.mark.asyncio
async def test_reset_password_service_unknown_token_raises_400():
    from fastapi import HTTPException

    db = make_mock_db()
    with pytest.raises(HTTPException) as exc_info:
        await reset_password(db, "bogus.jwt.value", "new-pw-123")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_service_inactive_user_raises_400():
    from fastapi import HTTPException

    user = make_user(is_active=False, hashed_password=hash_password("x"))
    raw_jwt = issue_password_reset_token(user.id, user.hashed_password)

    db = make_mock_db()
    db.get.return_value = user
    with pytest.raises(HTTPException) as exc_info:
        await reset_password(db, raw_jwt, "new-pw-123")
    assert exc_info.value.status_code == 400
