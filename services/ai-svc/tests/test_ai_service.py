"""Unit tests for app.services.ai_service.

Covers the Groq client lifecycle, the ``_ai_transform`` dispatch paths
(fake backend / Groq success / Groq failure / no key), the local fallback
functions, and the ``run_ai_tool`` / ``stream_ai_tool`` public entrypoints.

No real network calls are made - the Groq client and chat helpers are
mocked with ``unittest.mock`` throughout.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services import ai_service
from app.services.ai_prompts import FORMAT_PROMPTS, PROMPTS, TONE_INSTRUCTIONS

SAMPLE_TEXT = (
    "Python is a popular programming language used for web development, "
    "data science, and automation. FastAPI is a modern web framework for "
    "building APIs with Python. Testing ensures software quality."
)


def _chat_response(content: str):
    """Build a minimal object shaped like a Groq chat completion response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _stream_chunk(content):
    """Build a minimal object shaped like a Groq streaming chunk."""
    delta = SimpleNamespace(content=content) if content is not None else None
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


# ── Groq client lifecycle ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_groq_client_with_key(monkeypatch):
    """init_groq_client creates an AsyncGroq client when a key is set."""
    fake_client = MagicMock()
    monkeypatch.setattr(ai_service, "_groq_client", None)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "AsyncGroq", MagicMock(return_value=fake_client))

    ai_service.init_groq_client()
    assert ai_service._groq_client is fake_client


@pytest.mark.asyncio
async def test_init_groq_client_without_key(monkeypatch):
    """init_groq_client is a no-op when GROQ_API_KEY is empty."""
    monkeypatch.setattr(ai_service, "_groq_client", None)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")

    ai_service.init_groq_client()
    assert ai_service._groq_client is None


@pytest.mark.asyncio
async def test_close_groq_client(monkeypatch):
    """close_groq_client closes and clears the module-level client."""
    fake_client = AsyncMock()
    monkeypatch.setattr(ai_service, "_groq_client", fake_client)

    await ai_service.close_groq_client()
    fake_client.close.assert_awaited_once()
    assert ai_service._groq_client is None


@pytest.mark.asyncio
async def test_close_groq_client_noop_when_uninitialised(monkeypatch):
    """close_groq_client does nothing when the client was never created."""
    monkeypatch.setattr(ai_service, "_groq_client", None)
    await ai_service.close_groq_client()
    assert ai_service._groq_client is None


# ── _groq_chat / _groq_chat_stream ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_groq_chat_returns_stripped_content(monkeypatch):
    """_groq_chat returns the assistant message content, stripped."""
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        return_value=_chat_response("  hello there  ")
    )
    monkeypatch.setattr(ai_service, "_groq_client", fake_client)

    result = await ai_service._groq_chat("system", "user text")
    assert result == "hello there"
    fake_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_groq_chat_raises_when_client_uninitialised(monkeypatch):
    """_groq_chat raises RuntimeError when the client is not initialised."""
    monkeypatch.setattr(ai_service, "_groq_client", None)
    with pytest.raises(RuntimeError):
        await ai_service._groq_chat("system", "user text")


@pytest.mark.asyncio
async def test_groq_chat_stream_yields_token_chunks(monkeypatch):
    """_groq_chat_stream yields only chunks with non-empty delta content."""

    async def _aiter():
        for chunk in (
            _stream_chunk("Hel"),
            _stream_chunk(None),
            _stream_chunk(""),
            _stream_chunk("lo"),
        ):
            yield chunk

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_aiter())
    monkeypatch.setattr(ai_service, "_groq_client", fake_client)

    tokens = [t async for t in ai_service._groq_chat_stream("system", "text")]
    assert tokens == ["Hel", "lo"]


@pytest.mark.asyncio
async def test_groq_chat_stream_raises_when_client_uninitialised(monkeypatch):
    """_groq_chat_stream raises RuntimeError when the client is missing."""
    monkeypatch.setattr(ai_service, "_groq_client", None)
    agen = ai_service._groq_chat_stream("system", "text")
    with pytest.raises(RuntimeError):
        await anext(agen)


# ── _ai_transform dispatch paths ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_transform_fake_backend(monkeypatch):
    """AI_BACKEND=fake short-circuits to the deterministic fake response."""
    monkeypatch.setattr(settings, "AI_BACKEND", "fake")
    result = await ai_service._ai_transform(
        "prompt", "hello world", ai_service._passthrough_fallback
    )
    assert result == "[fake-ai] hello world"


@pytest.mark.asyncio
async def test_ai_transform_uses_groq_when_key_set(monkeypatch):
    """When a key is configured the Groq result is returned directly."""
    monkeypatch.setattr(settings, "AI_BACKEND", "auto")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "_groq_chat", AsyncMock(return_value="groq result"))

    result = await ai_service._ai_transform(
        "prompt", "hello", ai_service._passthrough_fallback
    )
    assert result == "groq result"


@pytest.mark.asyncio
async def test_ai_transform_falls_back_on_groq_error(monkeypatch):
    """A Groq failure falls back to the local function (never raises)."""
    monkeypatch.setattr(settings, "AI_BACKEND", "auto")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "_groq_chat", AsyncMock(side_effect=TimeoutError()))

    result = await ai_service._ai_transform(
        "prompt", "hello", lambda text: text.upper()
    )
    assert result == "HELLO"


@pytest.mark.asyncio
async def test_ai_transform_uses_fallback_without_key(monkeypatch):
    """No key configured → the local fallback runs immediately."""
    monkeypatch.setattr(settings, "AI_BACKEND", "auto")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")

    result = await ai_service._ai_transform(
        "prompt", "hello", lambda text: f"local:{text}"
    )
    assert result == "local:hello"


def test_fake_ai_response_snippets_first_line():
    """_fake_ai_response echoes the first line of the input, prefixed."""
    assert ai_service._fake_ai_response("p", "line one\nline two").endswith("line one")
    assert ai_service._fake_ai_response("p", "") == "[fake-ai]"


# ── Local fallback functions ──────────────────────────────────────────────────


def test_hashtag_fallback_produces_hashtags():
    result = ai_service._hashtag_fallback(SAMPLE_TEXT)
    assert result.startswith("#")
    assert " " in result


def test_seo_title_fallback_numbered_titles():
    result = ai_service._seo_title_fallback(SAMPLE_TEXT)
    assert result.startswith("1. ")
    assert "A Complete Guide" in result


def test_meta_description_fallback():
    result = ai_service._meta_description_fallback(SAMPLE_TEXT)
    assert "Discover everything about" in result


def test_blog_outline_fallback_structure():
    result = ai_service._blog_outline_fallback(SAMPLE_TEXT)
    assert result.startswith("# Blog Post:")
    assert "## Introduction" in result
    assert "## Conclusion" in result


def test_tweet_fallback_truncates_long_text():
    long_text = "word " * 100
    result = ai_service._tweet_fallback(long_text)
    assert result.endswith("...")
    assert len(result) <= 281


def test_email_fallback_wraps_text():
    result = ai_service._email_fallback("Meeting tomorrow\nPlease confirm.")
    assert result.startswith("Subject: Meeting tomorrow")
    assert "Best regards" in result


def test_keyword_fallback_returns_lines():
    result = ai_service._keyword_fallback(SAMPLE_TEXT)
    assert len(result.splitlines()) > 1


def test_ai_unavailable_fallback_raises_503():
    with pytest.raises(HTTPException) as exc:
        ai_service._ai_unavailable_fallback("some text")
    assert exc.value.status_code == 503


def test_summarize_fallback_first_three_sentences():
    text = "One. Two. Three. Four. Five."
    result = ai_service._summarize_fallback(text)
    assert result == "One. Two. Three...."


def test_grammar_fallback_capitalises_sentences():
    result = ai_service._grammar_fallback("hello world. this is a test.")
    assert result == "Hello world. This is a test."


def test_generate_title_fallback_numbered():
    result = ai_service._generate_title_fallback(SAMPLE_TEXT)
    assert result.startswith("1. ")


def test_sentiment_fallback_positive():
    result = ai_service._sentiment_fallback(
        "I am so happy and thrilled, this is wonderful and I am grateful"
    )
    assert "**Overall Sentiment:** Positive" in result


def test_sentiment_fallback_negative():
    result = ai_service._sentiment_fallback("I am sad and angry and miserable")
    assert "**Overall Sentiment:** Negative" in result


def test_sentiment_fallback_neutral_no_emotion_words():
    result = ai_service._sentiment_fallback("The table is made of wood")
    assert "**Overall Sentiment:** Neutral" in result
    assert "**Primary Emotion:** Neutral" in result


def test_passthrough_fallback_returns_text_unmodified():
    assert ai_service._passthrough_fallback("as-is", "extra") == "as-is"


# ── Format fallback ───────────────────────────────────────────────────────────

_FMT_TEXT = "First point. Second point. Third point. Fourth point."


def test_format_fallback_bullets():
    result = ai_service._format_fallback(_FMT_TEXT, "bullets")
    assert result.splitlines()[0] == "* First point."


def test_format_fallback_numbered():
    result = ai_service._format_fallback(_FMT_TEXT, "numbered")
    assert result.splitlines()[0] == "1. First point."
    assert result.splitlines()[3] == "4. Fourth point."


def test_format_fallback_paragraph_bullets():
    result = ai_service._format_fallback(_FMT_TEXT, "paragraph-bullets")
    assert result.startswith("First point.\n\n* Second point.")


def test_format_fallback_paragraph_bullets_single_sentence():
    assert ai_service._format_fallback("Only one.", "paragraph-bullets") == (
        "Only one."
    )


def test_format_fallback_tldr():
    result = ai_service._format_fallback(_FMT_TEXT, "tldr")
    assert result.startswith("TL;DR: First point.")
    assert _FMT_TEXT in result


def test_format_fallback_headings_groups_sentences():
    result = ai_service._format_fallback(_FMT_TEXT, "headings")
    assert "## Section 1" in result
    assert "## Section 2" in result


def test_format_fallback_default_paragraph():
    result = ai_service._format_fallback("One.\nTwo. Three.", "paragraph")
    assert result == "One. Two. Three."


# ── run_ai_tool dispatch ──────────────────────────────────────────────────────


@pytest.fixture
def captured_transform(monkeypatch):
    """Replace _ai_transform with a spy that records its arguments."""
    calls: dict = {}

    async def _fake_transform(prompt, text, fallback_fn, *extra, **kwargs):
        calls["prompt"] = prompt
        calls["text"] = text
        calls["extra"] = extra
        calls["kwargs"] = kwargs
        return "transformed"

    monkeypatch.setattr(ai_service, "_ai_transform", _fake_transform)
    return calls


@pytest.mark.asyncio
async def test_run_ai_tool_translate_builds_prompt(captured_transform):
    result = await ai_service.run_ai_tool("translate", "Hello", "French")
    assert result == "transformed"
    assert "French" in captured_transform["prompt"]
    assert captured_transform["text"] == "Hello"


@pytest.mark.asyncio
async def test_run_ai_tool_transliterate_builds_prompt(captured_transform):
    result = await ai_service.run_ai_tool("transliterate", "Hello", "Hindi")
    assert result == "transformed"
    assert "Hindi" in captured_transform["prompt"]
    assert "transliterat" in captured_transform["prompt"].lower()


@pytest.mark.asyncio
async def test_run_ai_tool_change_tone_known_tone(captured_transform):
    result = await ai_service.run_ai_tool("change-tone", "Hello", "casual")
    assert result == "transformed"
    assert TONE_INSTRUCTIONS["casual"] in captured_transform["prompt"]


@pytest.mark.asyncio
async def test_run_ai_tool_change_tone_unknown_tone_uses_formal(
    captured_transform,
):
    await ai_service.run_ai_tool("change-tone", "Hello", "no-such-tone")
    assert TONE_INSTRUCTIONS["formal"] in captured_transform["prompt"]


@pytest.mark.asyncio
async def test_run_ai_tool_change_format_builds_prompt(captured_transform):
    result = await ai_service.run_ai_tool("change-format", "Hello", "bullets")
    assert result == "transformed"
    assert FORMAT_PROMPTS["bullets"] in captured_transform["prompt"]


@pytest.mark.asyncio
async def test_run_ai_tool_static_tool_uses_registered_prompt(
    captured_transform,
):
    result = await ai_service.run_ai_tool("summarize", "Some text")
    assert result == "transformed"
    assert captured_transform["prompt"] == PROMPTS["summarize"]


@pytest.mark.asyncio
async def test_run_ai_tool_dynamic_tool_without_args_raises_key_error():
    with pytest.raises(KeyError):
        await ai_service.run_ai_tool("translate", "Hello")


@pytest.mark.asyncio
async def test_run_ai_tool_unknown_tool_raises_key_error():
    with pytest.raises(KeyError):
        await ai_service.run_ai_tool("no-such-tool", "Hello")


# ── stream_ai_tool ────────────────────────────────────────────────────────────


@pytest.fixture
def fake_stream(monkeypatch):
    """Replace _groq_chat_stream with a generator spy that records the prompt."""
    calls: dict = {}

    async def _fake(prompt, text, temperature, max_tokens):
        calls["prompt"] = prompt
        calls["text"] = text
        yield "tok1"
        yield "tok2"

    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "_groq_client", MagicMock())
    monkeypatch.setattr(ai_service, "_groq_chat_stream", _fake)
    return calls


@pytest.mark.asyncio
async def test_stream_ai_tool_without_key_falls_back_to_run(monkeypatch):
    """No Groq key → the full run_ai_tool result is yielded as one chunk."""
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(
        ai_service, "run_ai_tool", AsyncMock(return_value="full result")
    )

    chunks = [c async for c in ai_service.stream_ai_tool("summarize", "text")]
    assert chunks == ["full result"]


@pytest.mark.asyncio
async def test_stream_ai_tool_static_prompt(fake_stream):
    chunks = [c async for c in ai_service.stream_ai_tool("summarize", "text")]
    assert chunks == ["tok1", "tok2"]
    assert fake_stream["prompt"] == PROMPTS["summarize"]


@pytest.mark.asyncio
async def test_stream_ai_tool_translate_prompt(fake_stream):
    chunks = [c async for c in ai_service.stream_ai_tool("translate", "text", "German")]
    assert chunks == ["tok1", "tok2"]
    assert "German" in fake_stream["prompt"]


@pytest.mark.asyncio
async def test_stream_ai_tool_change_tone_prompt(fake_stream):
    chunks = [
        c async for c in ai_service.stream_ai_tool("change-tone", "text", "friendly")
    ]
    assert chunks == ["tok1", "tok2"]
    assert TONE_INSTRUCTIONS["friendly"] in fake_stream["prompt"]


@pytest.mark.asyncio
async def test_stream_ai_tool_change_format_prompt(fake_stream):
    chunks = [
        c async for c in ai_service.stream_ai_tool("change-format", "text", "numbered")
    ]
    assert chunks == ["tok1", "tok2"]
    assert FORMAT_PROMPTS["numbered"] in fake_stream["prompt"]


@pytest.mark.asyncio
async def test_stream_ai_tool_dynamic_without_args_falls_back(fake_stream, monkeypatch):
    """Parameterised tool with no args → single-chunk run_ai_tool fallback."""
    monkeypatch.setattr(
        ai_service, "run_ai_tool", AsyncMock(return_value="fallback result")
    )
    chunks = [c async for c in ai_service.stream_ai_tool("translate", "text")]
    assert chunks == ["fallback result"]
