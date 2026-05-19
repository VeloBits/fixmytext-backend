"""Tests for the ``get_verified_user`` dependency that gates AI endpoints.

Email verification (verify-email, resend-verification) is now handled by Keycloak.
These tests verify the email-verification gate behaviour on tool endpoints.
"""

from fastapi.testclient import TestClient
from main import app
from tests.conftest import make_mock_db, make_user

from app.core.deps import get_current_user, get_optional_user
from app.db.session import get_db

# ── Verification gate on tool endpoints ──────────────────────────────────────


def _post_tool(path: str, user, body: dict):
    """Helper: POST *body* to *path* as the given user (or visitor if None)."""

    async def _user_dep():
        return user

    async def _get_db():
        yield make_mock_db()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _user_dep
    app.dependency_overrides[get_optional_user] = _user_dep

    try:
        return TestClient(app, raise_server_exceptions=False).post(
            path, json=body, headers={}
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


def test_verified_user_can_access_tool():
    verified = make_user(is_email_verified=True)
    resp = _post_tool("/api/v1/text/uppercase", verified, {"text": "hello"})
    assert resp.status_code in (200, 201)
