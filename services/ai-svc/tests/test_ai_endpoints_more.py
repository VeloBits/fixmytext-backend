"""Additional endpoint tests for ai-svc.

Covers the paths not exercised by test_ai_endpoints.py / test_ai_auth.py:
- JWT verification success path (mocked verify_jwt_raw, no real Keycloak)
- Parameterised tools (translate / transliterate / change-tone / change-format)
- AI service failure → 500, HTTPException pass-through
- POST /ai/{tool_id}/stream happy path and error event
- POST /ai/{tool_id}/enqueue (mocked arq pool)
- GET /ai/jobs/{job_id} status derivation (complete / in_progress / failed)
- _get_arq_pool lazy singleton

Each test uses a unique user id so the shared in-memory rate limiter never
trips across the suite. All Groq / arq / payments-svc calls are mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _make_user(verified: bool = True):
    from app.api.v1.endpoints.ai import AuthenticatedUser

    return AuthenticatedUser(
        id=f"user-{uuid.uuid4()}",
        email="test@example.com",
        is_email_verified=verified,
    )


# ── JWT verification path (get_current_user) ──────────────────────────────────


@pytest.mark.asyncio
async def test_valid_jwt_reaches_tool(client):
    """A token accepted by verify_jwt_raw yields a 200 from the tool route."""
    sub = f"jwt-user-{uuid.uuid4()}"
    payload = {"sub": sub, "email": "jwt@example.com", "email_verified": True}

    with (
        patch(
            "app.api.v1.endpoints.ai.verify_jwt_raw",
            new=AsyncMock(return_value=payload),
        ),
        patch(
            "app.api.v1.endpoints.ai.check_entitlement",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.ai_service.run_ai_tool",
            new=AsyncMock(return_value="summary"),
        ),
    ):
        response = await client.post(
            "/api/v1/ai/summarize",
            headers={"Authorization": "Bearer good.jwt.token"},
            json={"text": "long article text"},
        )
    assert response.status_code == 200
    assert response.json()["result"] == "summary"


@pytest.mark.asyncio
async def test_jwt_without_sub_returns_401(client):
    """A verified token whose payload lacks ``sub`` must be rejected."""
    with patch(
        "app.api.v1.endpoints.ai.verify_jwt_raw",
        new=AsyncMock(return_value={"email": "nosub@example.com"}),
    ):
        response = await client.post(
            "/api/v1/ai/summarize",
            headers={"Authorization": "Bearer good.jwt.token"},
            json={"text": "hello"},
        )
    assert response.status_code == 401


# ── Parameterised tools ───────────────────────────────────────────────────────


async def _call_tool(client, tool_id: str, body: dict, result: str = "out"):
    """POST a tool with auth/entitlement/ai_service mocked; return response+mock."""
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    app.dependency_overrides[get_verified_user] = lambda: _make_user()
    ai_mock = AsyncMock(return_value=result)
    try:
        with (
            patch(
                "app.api.v1.endpoints.ai.check_entitlement",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("app.services.ai_service.run_ai_tool", new=ai_mock),
        ):
            response = await client.post(f"/api/v1/ai/{tool_id}", json=body)
    finally:
        app.dependency_overrides.clear()
    return response, ai_mock


@pytest.mark.asyncio
async def test_translate_operation_label_and_extra_args(client):
    response, ai_mock = await _call_tool(
        client,
        "translate",
        {"text": "Hello", "target_language": "French"},
        result="Bonjour",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "translate-french"
    assert body["result"] == "Bonjour"
    ai_mock.assert_awaited_once_with("translate", "Hello", "French")


@pytest.mark.asyncio
async def test_transliterate_operation_label(client):
    response, ai_mock = await _call_tool(
        client,
        "transliterate",
        {"text": "Hello", "target_language": "Hindi"},
    )
    assert response.status_code == 200
    assert response.json()["operation"] == "transliterate-hindi"
    ai_mock.assert_awaited_once_with("transliterate", "Hello", "Hindi")


@pytest.mark.asyncio
async def test_change_tone_operation_label(client):
    response, ai_mock = await _call_tool(
        client, "change-tone", {"text": "Hello", "tone": "Casual"}
    )
    assert response.status_code == 200
    assert response.json()["operation"] == "tone-casual"
    ai_mock.assert_awaited_once_with("change-tone", "Hello", "Casual")


@pytest.mark.asyncio
async def test_change_format_operation_label(client):
    response, ai_mock = await _call_tool(
        client, "change-format", {"text": "Hello", "format": "Bullets"}
    )
    assert response.status_code == 200
    assert response.json()["operation"] == "format-bullets"
    ai_mock.assert_awaited_once_with("change-format", "Hello", "Bullets")


@pytest.mark.asyncio
async def test_translate_missing_target_language_returns_422(client):
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    app.dependency_overrides[get_verified_user] = lambda: _make_user()
    try:
        response = await client.post("/api/v1/ai/translate", json={"text": "Hello"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


# ── AI service failure handling ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_service_generic_error_returns_500(client):
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    app.dependency_overrides[get_verified_user] = lambda: _make_user()
    try:
        with (
            patch(
                "app.api.v1.endpoints.ai.check_entitlement",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.ai_service.run_ai_tool",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            response = await client.post("/api/v1/ai/summarize", json={"text": "hello"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json()["detail"] == "Summarize failed"


@pytest.mark.asyncio
async def test_ai_service_http_exception_passes_through(client):
    """HTTPException raised by the service (e.g. 503 fallback) is not wrapped."""
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    app.dependency_overrides[get_verified_user] = lambda: _make_user()
    try:
        with (
            patch(
                "app.api.v1.endpoints.ai.check_entitlement",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.ai_service.run_ai_tool",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=503, detail="AI service temporarily unavailable."
                    )
                ),
            ),
        ):
            response = await client.post("/api/v1/ai/emojify", json={"text": "hello"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503


# ── POST /ai/{tool_id}/stream ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_yields_tokens_and_done(client):
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    def _fake_stream(tool_id, text, *extra_args):
        async def _gen():
            yield "Hello"
            yield " world"

        return _gen()

    app.dependency_overrides[get_verified_user] = lambda: _make_user()
    try:
        with (
            patch(
                "app.api.v1.endpoints.ai.check_entitlement",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("app.services.ai_service.stream_ai_tool", new=_fake_stream),
        ):
            response = await client.post(
                "/api/v1/ai/summarize/stream", json={"text": "hello"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: Hello\n\n" in response.text
    assert "data:  world\n\n" in response.text
    assert "data: [DONE]\n\n" in response.text


@pytest.mark.asyncio
async def test_stream_error_yields_error_event(client):
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    def _broken_stream(tool_id, text, *extra_args):
        async def _gen():
            raise RuntimeError("groq exploded")
            yield  # unreachable — present only to make this an async generator

        return _gen()

    app.dependency_overrides[get_verified_user] = lambda: _make_user()
    try:
        with (
            patch(
                "app.api.v1.endpoints.ai.check_entitlement",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("app.services.ai_service.stream_ai_tool", new=_broken_stream),
        ):
            response = await client.post(
                "/api/v1/ai/summarize/stream", json={"text": "hello"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "data: [ERROR] Internal server error\n\n" in response.text
    assert "groq exploded" not in response.text


# ── POST /ai/{tool_id}/enqueue ────────────────────────────────────────────────


async def _call_enqueue(client, tool_id: str, body: dict):
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    user = _make_user()
    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock(return_value=SimpleNamespace(job_id="job-123"))

    app.dependency_overrides[get_verified_user] = lambda: user
    try:
        with (
            patch(
                "app.api.v1.endpoints.ai.check_entitlement",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.api.v1.endpoints.ai._get_arq_pool",
                new_callable=AsyncMock,
                return_value=mock_pool,
            ),
        ):
            response = await client.post(f"/api/v1/ai/{tool_id}/enqueue", json=body)
    finally:
        app.dependency_overrides.clear()
    return response, mock_pool, user


@pytest.mark.asyncio
async def test_enqueue_returns_job_id(client):
    response, mock_pool, user = await _call_enqueue(
        client, "summarize", {"text": "hello"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "job-123"
    assert body["status"] == "queued"
    mock_pool.enqueue_job.assert_awaited_once_with(
        "run_ai_tool", "summarize", "hello", user.id, {}
    )


@pytest.mark.asyncio
async def test_enqueue_translate_includes_options(client):
    response, mock_pool, user = await _call_enqueue(
        client, "translate", {"text": "hello", "target_language": "German"}
    )
    assert response.status_code == 200
    mock_pool.enqueue_job.assert_awaited_once_with(
        "run_ai_tool", "translate", "hello", user.id, {"target_language": "German"}
    )


@pytest.mark.asyncio
async def test_enqueue_unknown_tool_returns_404(client):
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    app.dependency_overrides[get_verified_user] = lambda: _make_user()
    try:
        response = await client.post(
            "/api/v1/ai/no-such-tool/enqueue", json={"text": "hello"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_enqueue_blank_text_returns_422(client):
    from app.api.v1.endpoints.ai import get_verified_user
    from main import app

    app.dependency_overrides[get_verified_user] = lambda: _make_user()
    try:
        response = await client.post(
            "/api/v1/ai/summarize/enqueue", json={"text": "   "}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


# ── _get_arq_pool singleton ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_arq_pool_creates_pool_once(monkeypatch):
    from app.api.v1.endpoints import ai as ai_endpoints

    sentinel = MagicMock()
    create_mock = AsyncMock(return_value=sentinel)
    monkeypatch.setattr(ai_endpoints, "_arq_pool", None)
    monkeypatch.setattr(ai_endpoints, "create_pool", create_mock)

    first = await ai_endpoints._get_arq_pool()
    second = await ai_endpoints._get_arq_pool()

    assert first is sentinel
    assert second is sentinel
    create_mock.assert_awaited_once()


# ── GET /ai/jobs/{job_id} status derivation ──────────────────────────────────


async def _call_job_status(client, *, info, result=None, result_exc=None):
    """GET /jobs/{id} with a mocked arq job owned by the requesting user."""
    from app.api.v1.endpoints.ai import get_current_user
    from main import app

    user = _make_user()
    if info is not None:
        info.args = ["summarize", "text", user.id, {}]

    mock_job = AsyncMock()
    mock_job.info = AsyncMock(return_value=info)
    if result_exc is not None:
        mock_job.result = AsyncMock(side_effect=result_exc)
    else:
        mock_job.result = AsyncMock(return_value=result)

    mock_pool = AsyncMock()
    mock_pool.job = AsyncMock(return_value=mock_job)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.api.v1.endpoints.ai._get_arq_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            response = await client.get(
                "/api/v1/ai/jobs/job-xyz",
                headers={"Authorization": "Bearer valid.token"},
            )
    finally:
        app.dependency_overrides.clear()
    return response


@pytest.mark.asyncio
async def test_job_status_complete_returns_result(client):
    info = MagicMock()
    info.start_ms = 1
    info.finish_ms = 2
    info.success = True
    payload = {"original": "text", "result": "done", "operation": "summarize"}

    response = await _call_job_status(client, info=info, result=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["result"] == payload


@pytest.mark.asyncio
async def test_job_status_in_progress(client):
    info = MagicMock()
    info.start_ms = 1
    info.finish_ms = None
    info.success = None

    response = await _call_job_status(
        client, info=info, result_exc=TimeoutError("not done")
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_job_status_failed(client):
    info = MagicMock()
    info.start_ms = 1
    info.finish_ms = 2
    info.success = False

    response = await _call_job_status(
        client, info=info, result_exc=RuntimeError("job blew up")
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_job_status_info_none_returns_not_found(client):
    response = await _call_job_status(client, info=None)
    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
