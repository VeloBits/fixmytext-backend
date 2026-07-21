"""Unit tests for the arq worker tasks (app.worker.tasks).

The Groq layer is fully mocked — ``ai_service.run_ai_tool`` never makes a
real API call here.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.worker import tasks

# ── Startup / shutdown hooks ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_startup_initialises_groq_client():
    with patch("app.services.ai_service.init_groq_client") as init_mock:
        await tasks.startup({})
    init_mock.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_closes_groq_client():
    with patch(
        "app.services.ai_service.close_groq_client", new_callable=AsyncMock
    ) as close_mock:
        await tasks.shutdown({})
    close_mock.assert_awaited_once()


# ── run_ai_tool task ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_ai_tool_unknown_tool_raises_value_error():
    with pytest.raises(ValueError, match="not found"):
        await tasks.run_ai_tool({}, "no-such-tool", "text", "user-1")


@pytest.mark.asyncio
async def test_run_ai_tool_static_tool_returns_result_dict():
    with patch(
        "app.services.ai_service.run_ai_tool",
        new=AsyncMock(return_value="a summary"),
    ) as run_mock:
        result = await tasks.run_ai_tool({}, "summarize", "long text", "user-1")

    run_mock.assert_awaited_once_with("summarize", "long text")
    assert result == {
        "original": "long text",
        "result": "a summary",
        "operation": "summarize",
    }


@pytest.mark.asyncio
async def test_run_ai_tool_translate_passes_language_and_labels_operation():
    with patch(
        "app.services.ai_service.run_ai_tool",
        new=AsyncMock(return_value="Bonjour"),
    ) as run_mock:
        result = await tasks.run_ai_tool(
            {},
            "translate",
            "Hello",
            "user-1",
            {"target_language": "French"},
        )

    run_mock.assert_awaited_once_with("translate", "Hello", "French")
    assert result["operation"] == "translate-french"
    assert result["result"] == "Bonjour"


@pytest.mark.asyncio
async def test_run_ai_tool_change_tone_labels_operation():
    with patch(
        "app.services.ai_service.run_ai_tool",
        new=AsyncMock(return_value="Hey there"),
    ) as run_mock:
        result = await tasks.run_ai_tool(
            {}, "change-tone", "Hello", "user-1", {"tone": "Casual"}
        )

    run_mock.assert_awaited_once_with("change-tone", "Hello", "Casual")
    assert result["operation"] == "tone-casual"


@pytest.mark.asyncio
async def test_run_ai_tool_change_format_labels_operation():
    with patch(
        "app.services.ai_service.run_ai_tool",
        new=AsyncMock(return_value="* Hello"),
    ) as run_mock:
        result = await tasks.run_ai_tool(
            {}, "change-format", "Hello", "user-1", {"format": "Bullets"}
        )

    run_mock.assert_awaited_once_with("change-format", "Hello", "Bullets")
    assert result["operation"] == "format-bullets"


@pytest.mark.asyncio
async def test_run_ai_tool_options_none_defaults_to_empty():
    with patch(
        "app.services.ai_service.run_ai_tool",
        new=AsyncMock(return_value="out"),
    ) as run_mock:
        result = await tasks.run_ai_tool({}, "fix-grammar", "some text", "user-1", None)

    run_mock.assert_awaited_once_with("fix-grammar", "some text")
    assert result["operation"] == "fix-grammar"


# ── WorkerSettings ────────────────────────────────────────────────────────────


def test_worker_settings_configuration():
    assert tasks.WorkerSettings.functions == [tasks.run_ai_tool]
    assert tasks.WorkerSettings.on_startup is tasks.startup
    assert tasks.WorkerSettings.on_shutdown is tasks.shutdown
    assert tasks.WorkerSettings.keep_result == 3600
    assert tasks.WorkerSettings.job_timeout == 120


def test_worker_main_reexports_worker_settings():
    from app.worker.main import WorkerSettings

    assert WorkerSettings is tasks.WorkerSettings
