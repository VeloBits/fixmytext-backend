"""Tests for /auth/verify-email, /auth/resend-verification, and the
``get_verified_user`` dependency that gates AI endpoints.

Tokens are JWTs issued by ``app.core.transactional_tokens``. There is no
DB token table — verification is stateless. The cooldown for resend lives
in ``verification_resend_limiter`` (Redis-backed in prod, in-memory by
default in tests).
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import create_access_token
from app.core.transactional_tokens import issue_email_verification_token
from app.db.session import get_db
from app.services.auth_service import (
    resend_verification,
    verify_email,
)
from main import app
from tests.conftest import make_mock_db, make_user

# ── /auth/verify-email ────────────────────────────────────────────────────────


def test_verify_email_valid_flow_marks_user_verified():
    user = make_user(is_email_verified=False)
    raw_jwt = issue_email_verification_token(user.id)

    db = make_mock_db()
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/verify-email", json={"token": raw_jwt}
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert user.is_email_verified is True
    db.commit.assert_awaited()


def test_verify_email_unknown_or_malformed_token_returns_400():
    db = make_mock_db()

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/verify-email", json={"token": "totally.bogus.token"}
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_verify_email_wrong_purpose_token_returns_400():
    """A JWT issued for a different flow (e.g. an access token) must be
    rejected even though it's signed by the same secret."""
    user = make_user(is_email_verified=False)
    access_token = create_access_token(user.id)  # purpose != email-verify

    db = make_mock_db()
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/verify-email", json={"token": access_token}
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert user.is_email_verified is False


def test_verify_email_idempotent_for_already_verified_user():
    """Re-verifying a verified user is a no-op and still returns 200."""
    user = make_user(is_email_verified=True)
    raw_jwt = issue_email_verification_token(user.id)

    db = make_mock_db()
    db.get.return_value = user

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/verify-email", json={"token": raw_jwt}
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert user.is_email_verified is True


def test_verify_email_missing_token_rejected_by_validation():
    resp = TestClient(app).post("/api/v1/auth/verify-email", json={})
    assert resp.status_code == 422


# ── /auth/resend-verification ─────────────────────────────────────────────────


def _swap_in_fresh_resend_limiter(monkeypatch, max_requests=1, window_seconds=120):
    """Replace the module-level resend limiter with a fresh in-memory one so
    each test starts in a known state. Returns the new limiter so callers
    can assert against it."""
    limiter = InMemoryRateLimiter(
        max_requests=max_requests, window_seconds=window_seconds
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.verification_resend_limiter", limiter
    )
    return limiter


def test_resend_verification_issues_new_token(monkeypatch):
    monkeypatch.setattr("app.api.v1.endpoints.auth.settings.EMAIL_BACKEND", "console")
    monkeypatch.setattr("app.api.v1.endpoints.auth.settings.SMTP_HOST", "")
    _swap_in_fresh_resend_limiter(monkeypatch)

    user = make_user(is_email_verified=False)
    db = make_mock_db()

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
    echoed = data["verification_token"]
    assert echoed and echoed.count(".") == 2  # JWT echoed in console mode
    assert mock_send.await_count == 1
    sent_user, sent_token = mock_send.await_args.args
    assert sent_user.id == user.id
    assert sent_token == echoed


def test_resend_verification_respects_per_user_cooldown_returns_429(monkeypatch):
    """The 2nd call inside the per-user window must be rejected with 429."""
    _swap_in_fresh_resend_limiter(monkeypatch, max_requests=1, window_seconds=120)

    user = make_user(is_email_verified=False)
    db = make_mock_db()

    async def _get_db():
        yield db

    async def _user_dep():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _user_dep

    access = create_access_token(user.id)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {access}"}

    with patch(
        "app.api.v1.endpoints.auth.send_verification_email", new_callable=AsyncMock
    ):
        first = client.post("/api/v1/auth/resend-verification", headers=headers)
        second = client.post("/api/v1/auth/resend-verification", headers=headers)
    app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 429


def test_resend_verification_allows_after_cooldown_window(monkeypatch):
    """A wide-open window (1 request / 1s) admits two consecutive requests
    once the first has aged out — ensures the limiter is keyed correctly."""
    import time

    _swap_in_fresh_resend_limiter(monkeypatch, max_requests=1, window_seconds=1)

    user = make_user(is_email_verified=False)
    db = make_mock_db()

    async def _get_db():
        yield db

    async def _user_dep():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _user_dep

    access = create_access_token(user.id)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {access}"}

    with patch(
        "app.api.v1.endpoints.auth.send_verification_email", new_callable=AsyncMock
    ):
        first = client.post("/api/v1/auth/resend-verification", headers=headers)
        time.sleep(1.1)
        second = client.post("/api/v1/auth/resend-verification", headers=headers)
    app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200


def test_resend_verification_noop_for_already_verified_user(monkeypatch):
    _swap_in_fresh_resend_limiter(monkeypatch)
    user = make_user(is_email_verified=True)
    db = make_mock_db()

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
    # No token in body and no email sent for an already-verified account.
    assert resp.json()["verification_token"] is None
    mock_send.assert_not_awaited()


def test_resend_verification_requires_auth():
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/resend-verification"
    )
    assert resp.status_code == 401


# ── Verification gate on tool endpoints ──────────────────────────────────────


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
    unverified = make_user(is_email_verified=False)
    resp = _post_tool("/api/v1/text/uppercase", unverified, {"text": "hello"})
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert isinstance(detail, dict) and detail.get("code") == "email_not_verified"


def test_local_tool_allows_visitors():
    """Anonymous visitors keep free-tier access; only authed-but-unverified
    users are blocked."""
    resp = _post_tool("/api/v1/text/uppercase", None, {"text": "hello"})
    assert resp.status_code != 403


# ── Service-layer unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_email_service_happy_path():
    user = make_user(is_email_verified=False)
    raw_jwt = issue_email_verification_token(user.id)
    db = make_mock_db()
    db.get.return_value = user

    updated = await verify_email(db, raw_jwt)
    assert updated.is_email_verified is True


@pytest.mark.asyncio
async def test_verify_email_service_malformed_token_raises_400():
    from fastapi import HTTPException

    db = make_mock_db()
    with pytest.raises(HTTPException) as exc_info:
        await verify_email(db, "bogus")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_resend_verification_service_already_verified_returns_none():
    user = make_user(is_email_verified=True)
    result = await resend_verification(user)
    assert result is None


@pytest.mark.asyncio
async def test_resend_verification_service_returns_jwt_for_unverified_user():
    user = make_user(is_email_verified=False)
    raw_jwt = await resend_verification(user)
    assert raw_jwt and raw_jwt.count(".") == 2
