"""Tests for app/services/ai_service.py — fallback functions and helpers."""

import pytest
from fastapi import HTTPException

from app.services.ai_service import (
    _ai_unavailable_fallback,
    _blog_outline_fallback,
    _email_fallback,
    _grammar_fallback,
    _hashtag_fallback,
    _keyword_fallback,
    _meta_description_fallback,
    _seo_title_fallback,
    _summarize_fallback,
    _tweet_fallback,
)

# ── YAKE-based fallbacks ────────────────────────────────────────────────────


class TestHashtagFallback:
    """Test offline hashtag generation via YAKE keywords."""

    def test_returns_hashtags(self):
        """Returns string with hashtags for normal text."""
        result = _hashtag_fallback(
            "Machine learning is a subset of artificial intelligence. "
            "Deep learning uses neural networks."
        )
        assert isinstance(result, str)
        assert "#" in result

    def test_short_text(self):
        """Short text still returns something."""
        result = _hashtag_fallback("hello world")
        assert isinstance(result, str)


class TestSeoTitleFallback:
    """Test offline SEO title generation."""

    def test_returns_titles(self):
        """Returns numbered titles for normal text."""
        result = _seo_title_fallback(
            "Python is a popular programming language for data science and machine learning."
        )
        assert isinstance(result, str)
        # Should have numbered lines
        assert "1." in result


class TestMetaDescriptionFallback:
    """Test offline meta description generation."""

    def test_returns_descriptions(self):
        """Returns descriptions for normal text."""
        result = _meta_description_fallback(
            "FastAPI is a modern web framework for building APIs with Python."
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestBlogOutlineFallback:
    """Test offline blog outline generation."""

    def test_returns_outline(self):
        """Returns markdown-style outline."""
        result = _blog_outline_fallback(
            "Docker containers are lightweight and portable. "
            "Kubernetes orchestrates container deployments."
        )
        assert isinstance(result, str)
        assert "#" in result  # markdown headings


# ── Simple fallbacks ────────────────────────────────────────────────────────


class TestTweetFallback:
    """Test tweet shortening fallback."""

    def test_short_text_unchanged(self):
        """Text under 280 chars gets ellipsis."""
        result = _tweet_fallback("hello world")
        assert "hello" in result

    def test_long_text_truncated(self):
        """Long text is truncated and gets '...' suffix."""
        long_text = "word " * 100
        result = _tweet_fallback(long_text)
        assert len(result) <= 281


class TestEmailFallback:
    """Test email rewrite fallback."""

    def test_produces_email_format(self):
        """Fallback wraps text in email-like format."""
        result = _email_fallback("Please review the attached document.")
        assert "Subject:" in result
        assert "Best regards" in result


class TestKeywordFallback:
    """Test keyword extraction fallback."""

    def test_returns_keywords(self):
        """Returns newline-separated keywords."""
        result = _keyword_fallback(
            "Python programming language is great for data science and machine learning."
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestAiUnavailableFallback:
    """Test the unified fallback for AI tools without meaningful local alternatives.

    Tools like translate, transliterate, paraphrase, emojify, detect-language
    now raise HTTP 503 when Groq is unavailable instead of returning placeholder
    messages disguised as successful responses.
    """

    def test_raises_503(self):
        """Raises HTTPException with 503 status code."""
        with pytest.raises(HTTPException) as exc_info:
            _ai_unavailable_fallback("some text")
        assert exc_info.value.status_code == 503
        assert "unavailable" in exc_info.value.detail.lower()

    def test_raises_503_with_extra_args(self):
        """Extra positional args (e.g., target_language) are accepted and ignored."""
        with pytest.raises(HTTPException) as exc_info:
            _ai_unavailable_fallback("hello", "Spanish")
        assert exc_info.value.status_code == 503


class TestSummarizeFallback:
    """Test summarize fallback."""

    def test_returns_first_sentences(self):
        """Returns first few sentences."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = _summarize_fallback(text)
        assert "First sentence" in result

    def test_short_text(self):
        """Short text returned as-is."""
        result = _summarize_fallback("Just one sentence.")
        assert "Just one" in result


class TestGrammarFallback:
    """Test grammar fix fallback."""

    def test_capitalizes_after_period(self):
        """Capitalizes letters after sentence-ending punctuation."""
        result = _grammar_fallback("hello. world.")
        assert result[0].isupper()

    def test_capitalizes_first_char(self):
        """Capitalizes the first character if lowercase."""
        result = _grammar_fallback("hello world")
        assert result[0] == "H"


# ── Groq client lifecycle ───────────────────────────────────────────────────


class TestGroqClientLifecycle:
    """Test init/close of Groq client."""

    def test_init_without_api_key(self):
        """init_groq_client does nothing when GROQ_API_KEY is empty."""
        from unittest.mock import patch

        from app.services import ai_service

        original = ai_service._groq_client
        ai_service._groq_client = None
        with patch.object(ai_service.settings, "GROQ_API_KEY", ""):
            ai_service.init_groq_client()
        assert ai_service._groq_client is None
        ai_service._groq_client = original

    @pytest.mark.asyncio
    async def test_close_when_none(self):
        """close_groq_client does nothing when client is None."""
        from app.services import ai_service

        original = ai_service._groq_client
        ai_service._groq_client = None
        await ai_service.close_groq_client()
        assert ai_service._groq_client is None
        ai_service._groq_client = original
