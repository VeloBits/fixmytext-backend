"""Auth degradation tests for text-svc.

text-svc uses optional JWT auth: an invalid/missing Bearer token silently
downgrades to the visitor quota path rather than returning 401. These tests
verify that contract and the valid-JWT user-quota path.

Complements test_text_endpoints.py (tool dispatch) and
test_entitlement_gate.py (entitlement check_access mocking).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_PAYLOAD = {
    "sub": "11111111-1111-1111-1111-111111111111",
    "email": "auth@example.com",
    "email_verified": True,
}


def _make_entitlement_ok():
    """Patch check_entitlement in text-svc to allow access.

    text.py imports: ``from app.services.entitlement_client import check_access as check_entitlement``
    so the bound name in the module is ``check_entitlement``.
    """
    return patch(
        "app.api.v1.endpoints.text.check_entitlement",
        new_callable=AsyncMock,
        return_value=None,
    )


def _make_rate_limit_ok():
    """Patch rate limiters to not raise."""
    return patch(
        "app.api.v1.endpoints.text.text_limiter",
        new=MagicMock(check=AsyncMock()),
    )


# ── No credentials → visitor path ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_auth_falls_through_to_visitor_path(client):
    """POST with no Authorization header uses visitor quota — no 401."""
    with _make_entitlement_ok(), _make_rate_limit_ok():
        response = await client.post(
            "/api/v1/text/uppercase",
            json={"text": "hello"},
        )
    # Visitor quota accepted → 200 (tool executes)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_jwt_falls_through_to_visitor_path(client):
    """An invalid Bearer token is silently downgraded to visitor quota — no 401."""
    with patch(
        "fixmytext_shared.security.jwt.verify_jwt_raw",
        side_effect=Exception("bad jwt"),
    ):
        with _make_entitlement_ok(), _make_rate_limit_ok():
            response = await client.post(
                "/api/v1/text/uppercase",
                headers={"Authorization": "Bearer bad.token.here"},
                json={"text": "hello"},
            )
    assert response.status_code == 200


# ── Valid JWT → authenticated user path ──────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_jwt_identifies_user_for_entitlement(client):
    """A valid Bearer JWT identifies the caller so entitlement check receives user_id.

    Verifies that the OptionalUser returned from get_optional_user contains the
    correct Keycloak sub — used by the entitlement gate to apply per-user quota.
    """
    captured: list[dict] = []

    async def _capture_check_access(**kwargs):
        captured.append(kwargs)

    # KEYCLOAK_JWKS_URL must be set; auth.py skips JWT if it's empty (returns None/visitor)
    with patch("app.core.auth.settings") as mock_settings:
        mock_settings.KEYCLOAK_JWKS_URL = "http://keycloak/jwks"
        mock_settings.KEYCLOAK_AUDIENCE = None
        mock_settings.KEYCLOAK_ISSUER = None
        with patch(
            "app.core.auth.verify_jwt_raw",
            return_value=_VALID_PAYLOAD,
        ):
            with patch(
                "app.api.v1.endpoints.text.check_entitlement",
                side_effect=_capture_check_access,
            ):
                with _make_rate_limit_ok():
                    response = await client.post(
                        "/api/v1/text/uppercase",
                        headers={"Authorization": "Bearer valid.token"},
                        json={"text": "hello"},
                    )

    assert response.status_code == 200
    assert len(captured) == 1
    # entitlement gate must see the authenticated user (not None/visitor)
    # check_entitlement is called with user=OptionalUser(...) where user.id == sub
    user_arg = captured[0].get("user")
    assert user_arg is not None
    assert user_arg.id == _VALID_PAYLOAD["sub"]


# ── Entitlement denial ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quota_exhausted_returns_402(client):
    """When check_access raises HTTPException(402), text endpoint returns 402."""
    from fastapi import HTTPException

    with _make_rate_limit_ok():
        with patch(
            "app.api.v1.endpoints.text.check_entitlement",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=402, detail="quota exhausted"),
        ):
            response = await client.post(
                "/api/v1/text/uppercase",
                json={"text": "hello"},
            )
    assert response.status_code == 402
