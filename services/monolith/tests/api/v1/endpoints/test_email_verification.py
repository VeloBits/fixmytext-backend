"""Tests for the ``get_verified_user`` dependency that gates AI endpoints.

Email verification (verify-email, resend-verification) is now handled by Keycloak.
These tests verify the email-verification gate behaviour on the AI service endpoints.

Note: Local text tool endpoints have moved to text-svc (Sprint 4e). The
corresponding tests for those endpoints now live in
``services/text-svc/tests/test_text_endpoints.py``.
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
