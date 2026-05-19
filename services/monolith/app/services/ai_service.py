"""
AIService -- AI-powered text tools.

Primary: Groq API (Llama 3.3 70B) for context-aware generation.
Fallback: YAKE keyword extraction for offline / no-key usage.

All public AI tools are dispatched through ``run_ai_tool(tool_id, text, ...)``.
The per-tool prompts, fallback functions, and generation parameters are stored
in ``_AI_HANDLERS`` so that adding a new tool is a single dict entry.
"""

import asyncio
import logging
import re
from collections.abc import Callable
from typing import Any

import yake
from groq import APIError, APITimeoutError, AsyncGroq

from app.core.config import settings
from app.services.ai_prompts import FORMAT_PROMPTS, PROMPTS, TONE_INSTRUCTIONS

logger = logging.getLogger(__name__)


# ── Groq helpers ──────────────────────────────────────────────────────────────


_groq_client: AsyncGroq | None = None


def init_groq_client() -> None:
    """Initialize the Groq client (called from FastAPI lifespan)."""
    global _groq_client  # noqa: PLW0603
    if settings.GROQ_API_KEY:
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY, timeout=30.0)


async def close_groq_client() -> None:
    """Close the Groq client (called from FastAPI lifespan)."""
    global _groq_client  # noqa: PLW0603
    if _groq_client is not None:
        await _groq_client.close()
        _groq_client = None


async def _groq_chat(
    system_prompt: str,
    user_text: str,
    temperature: float = 0.7,
    max_tokens: int = 200,
) -> str:
    """Send a single chat completion to Groq and return the assistant text."""
    client = _groq_client
    response = await client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


async def _groq_chat_stream(
    system_prompt: str,
    user_text: str,
    temperature: float = 0.7,
    max_tokens: int = 200,
):
    """Yield token chunks from Groq streaming API for Server-Sent Events."""
    client = _groq_client
    if client is None:
        raise RuntimeError("Groq client not initialized")
    stream = await client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


def _fake_ai_response(system_prompt: str, text: str) -> str:
    """Deterministic stand-in for Groq, used when AI_BACKEND=fake (E2E tests)."""
    snippet = (text or "").strip().splitlines()[0][:80] if text else ""
    return f"[fake-ai] {snippet}".strip()


async def _ai_transform(
    system_prompt: str,
    text: str,
    fallback_fn: Callable[..., str],
    *fallback_args: Any,
    temperature: float = 0.7,
    max_tokens: int = 200,
) -> str:
    """Unified AI transform: try Groq first, fall back to a local function."""
    if settings.AI_BACKEND.lower() == "fake":
        return _fake_ai_response(system_prompt, text)
    if settings.GROQ_API_KEY:
        try:
            async with asyncio.timeout(35):
                return await _groq_chat(system_prompt, text, temperature, max_tokens)
        except (TimeoutError, APIError, APITimeoutError) as exc:
            logger.warning(
                "Groq API call failed, using fallback: %s", type(exc).__name__
            )
    return await asyncio.to_thread(fallback_fn, text, *fallback_args)


# ── YAKE helper ───────────────────────────────────────────────────────────────


_yake_extractor = None


def _get_yake():
    """Return a cached YAKE KeywordExtractor (created once, reused)."""
    global _yake_extractor  # noqa: PLW0603
    if _yake_extractor is None:
        _yake_extractor = yake.KeywordExtractor(lan="en", n=2, top=20, dedupLim=0.7)
    return _yake_extractor


def _yake_keywords_sync(text: str, top: int = 10) -> list[str]:
    """Extract top keywords via YAKE (synchronous)."""
    return [kw for kw, _score in _get_yake().extract_keywords(text)][:top]


# ── Fallback functions ────────────────────────────────────────────────────────


def _hashtag_fallback(text: str) -> str:
    keywords = _yake_keywords_sync(text)
    return " ".join(f"#{kw.replace(' ', '').capitalize()}" for kw in keywords[:10])


def _seo_title_fallback(text: str) -> str:
    keywords = _yake_keywords_sync(text, top=5)
    return "\n".join(
        f"{i}. {kw.title()} -- A Complete Guide" for i, kw in enumerate(keywords[:5], 1)
    )


def _meta_description_fallback(text: str) -> str:
    keywords = _yake_keywords_sync(text, top=3)
    return "\n".join(
        f"{i}. Discover everything about {kw}. "
        "Read our comprehensive guide and learn key insights today."
        for i, kw in enumerate(keywords[:3], 1)
    )


def _blog_outline_fallback(text: str) -> str:
    keywords = _yake_keywords_sync(text, top=5)
    topic = keywords[0].title() if keywords else "Your Topic"
    sections = [
        f"# Blog Post: {topic}",
        "",
        "## Introduction",
        f"- Hook: Why {topic} matters",
        "- Brief overview of key points",
        "",
    ]
    for i, kw in enumerate(keywords[1:5], 1):
        sections.append(f"## {i}. {kw.title()}")
        sections.append(f"- Key insight about {kw}")
        sections.append("- Practical tips and examples")
        sections.append("")
    sections.extend(["## Conclusion", "- Summary of key takeaways", "- Call to action"])
    return "\n".join(sections)


def _tweet_fallback(text: str) -> str:
    truncated = text[:277]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + "..."


def _email_fallback(text: str) -> str:
    lines = text.strip().split("\n")
    subject = lines[0][:60] if lines else "Follow-up"
    body = text.strip()
    return f"Subject: {subject}\n\nDear recipient,\n\n{body}\n\nBest regards"


def _keyword_fallback(text: str) -> str:
    keywords = _yake_keywords_sync(text, top=15)
    return "\n".join(keywords)


def _ai_unavailable_fallback(text: str, *_args: Any) -> str:
    """Raise 503 when Groq is unavailable and no meaningful local fallback exists."""
    from fastapi import HTTPException

    raise HTTPException(
        status_code=503,
        detail="AI service temporarily unavailable. Please try again later.",
    )


def _summarize_fallback(text: str) -> str:
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()
    ]
    return " ".join(sentences[:3]) + ("..." if len(sentences) > 3 else "")


def _grammar_fallback(text: str) -> str:
    result = re.sub(
        r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text
    )
    if result and result[0].islower():
        result = result[0].upper() + result[1:]
    return result


def _generate_title_fallback(text: str) -> str:
    keywords = _yake_keywords_sync(text, top=5)
    return "\n".join(f"{i}. {kw.title()}" for i, kw in enumerate(keywords[:5], 1))


# Emotion keywords used by the sentiment-analysis fallback.
_EMOTION_KEYWORDS: dict[str, set[str]] = {
    "happy": {
        "happy",
        "glad",
        "joy",
        "joyful",
        "cheerful",
        "delighted",
        "excited",
        "thrilled",
        "elated",
        "ecstatic",
        "pleased",
        "wonderful",
        "fantastic",
    },
    "sad": {
        "sad",
        "unhappy",
        "depressed",
        "miserable",
        "heartbroken",
        "grief",
        "sorrow",
        "gloomy",
        "melancholy",
        "lonely",
        "crying",
        "tears",
    },
    "angry": {
        "angry",
        "furious",
        "rage",
        "mad",
        "annoyed",
        "frustrated",
        "irritated",
        "outraged",
        "hostile",
        "livid",
        "infuriated",
        "hate",
    },
    "fearful": {
        "afraid",
        "scared",
        "fear",
        "terrified",
        "anxious",
        "worried",
        "nervous",
        "panic",
        "dread",
        "frightened",
        "alarmed",
        "uneasy",
    },
    "surprised": {
        "surprised",
        "shocked",
        "amazed",
        "astonished",
        "stunned",
        "unexpected",
        "unbelievable",
        "wow",
        "whoa",
        "incredible",
    },
    "disgusted": {
        "disgusted",
        "gross",
        "revolting",
        "repulsive",
        "sickening",
        "vile",
        "nasty",
        "horrible",
        "appalling",
        "dreadful",
    },
    "hopeful": {
        "hope",
        "hopeful",
        "optimistic",
        "promising",
        "encouraged",
        "looking forward",
        "bright",
        "positive",
        "confident",
        "inspired",
    },
    "loving": {
        "love",
        "adore",
        "cherish",
        "affection",
        "caring",
        "devoted",
        "passionate",
        "romantic",
        "warm",
        "tender",
        "fond",
    },
    "grateful": {
        "grateful",
        "thankful",
        "appreciate",
        "blessed",
        "thank",
        "thanks",
        "gratitude",
        "indebted",
    },
    "confused": {
        "confused",
        "puzzled",
        "baffled",
        "bewildered",
        "perplexed",
        "unclear",
        "lost",
        "uncertain",
        "unsure",
    },
}


def _sentiment_fallback(text: str) -> str:
    """Keyword-based sentiment analysis used when Groq is unavailable."""
    words = set(text.lower().split())
    detected: dict[str, int] = {}
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        count = len(words & keywords)
        if count > 0:
            detected[emotion] = count

    pos_emotions = {"happy", "hopeful", "loving", "grateful", "surprised"}
    neg_emotions = {"sad", "angry", "fearful", "disgusted"}
    pos_score = sum(v for k, v in detected.items() if k in pos_emotions)
    neg_score = sum(v for k, v in detected.items() if k in neg_emotions)

    if pos_score > neg_score:
        sentiment = "Positive"
    elif neg_score > pos_score:
        sentiment = "Negative"
    else:
        sentiment = "Neutral"

    sorted_emotions = sorted(detected.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_emotions[0][0].title() if sorted_emotions else "Neutral"
    secondary = (
        ", ".join(e.title() for e, _ in sorted_emotions[1:3])
        if len(sorted_emotions) > 1
        else "None detected"
    )
    return "\n".join(
        [
            f"**Overall Sentiment:** {sentiment}",
            "**Confidence:** Low (keyword-based fallback)",
            f"**Primary Emotion:** {primary}",
            f"**Secondary Emotions:** {secondary}",
            "**Sarcasm Detected:** Cannot detect (requires AI)",
            "**Tone:** Cannot detect (requires AI)",
            "",
            "Note: Set GROQ_API_KEY for full AI-powered analysis with sarcasm detection and tone analysis.",
        ]
    )


# Prompt dicts are imported from app.services.ai_prompts; aliased here for
# internal use (private-name convention matches the rest of this module).
_FORMAT_PROMPTS = FORMAT_PROMPTS


def _format_fallback(text: str, fmt: str) -> str:
    """Local-only format changer when Groq is unavailable."""
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()
    ]
    if fmt == "bullets":
        return "\n".join(f"* {s}" for s in sentences)
    if fmt == "numbered":
        return "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, 1))
    if fmt == "paragraph-bullets":
        if len(sentences) > 1:
            return sentences[0] + "\n\n" + "\n".join(f"* {s}" for s in sentences[1:])
        return text
    if fmt == "tldr":
        summary = sentences[0] if sentences else text[:100]
        return f"TL;DR: {summary}\n\n{text}"
    if fmt == "headings":
        chunks: list[list[str]] = []
        chunk: list[str] = []
        for s in sentences:
            chunk.append(s)
            if len(chunk) >= 3:
                chunks.append(chunk)
                chunk = []
        if chunk:
            chunks.append(chunk)
        result_lines: list[str] = []
        for i, c in enumerate(chunks, 1):
            result_lines.append(f"## Section {i}")
            result_lines.append(" ".join(c))
            result_lines.append("")
        return "\n".join(result_lines)
    # default: paragraph
    return " ".join(sentences)


def _passthrough_fallback(text: str, *_args: Any) -> str:
    """Return text unmodified -- used when no meaningful offline fallback exists."""
    return text


_TONE_INSTRUCTIONS = TONE_INSTRUCTIONS


_PROMPTS = PROMPTS


# ── AI handler registry ───────────────────────────────────────────────────────
#
# Each entry maps a *tool_id* (the same slug used in the URL) to:
#   (prompt_key, fallback_fn, extra_fallback_args, ai_kwargs)
#
# ``extra_fallback_args`` is a tuple of extra positional args passed to the
# fallback function *after* the text.  ``ai_kwargs`` overrides the default
# temperature / max_tokens passed to ``_ai_transform``.
#
# For tools whose prompt is built dynamically (translate, transliterate,
# change-tone, change-format) we use ``None`` as prompt_key and handle
# them specially in ``run_ai_tool``.

_AI_HANDLERS: dict[
    str,
    tuple[str | None, Callable[..., str], tuple[Any, ...], dict[str, Any]],
] = {
    # tool_id: (prompt_key, fallback_fn, extra_fallback_args, ai_kwargs)
    "generate-hashtags": ("hashtags", _hashtag_fallback, (), {}),
    "generate-seo-titles": (
        "seo_titles",
        _seo_title_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 300},
    ),
    "generate-meta-descriptions": (
        "meta_descriptions",
        _meta_description_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 400},
    ),
    "generate-blog-outline": (
        "blog_outline",
        _blog_outline_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 600},
    ),
    "shorten-for-tweet": ("tweet", _tweet_fallback, (), {"max_tokens": 100}),
    "rewrite-email": ("email", _email_fallback, (), {"max_tokens": 500}),
    "extract-keywords": ("keywords", _keyword_fallback, (), {"temperature": 0.3}),
    # translate and transliterate are handled dynamically
    "translate": (
        None,
        _ai_unavailable_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 1000},
    ),
    "transliterate": (
        None,
        _ai_unavailable_fallback,
        (),
        {"temperature": 0.2, "max_tokens": 1000},
    ),
    "emojify": (
        "emojify",
        _ai_unavailable_fallback,
        (),
        {"temperature": 0.7, "max_tokens": 1000},
    ),
    "detect-language": (
        "detect_language",
        _ai_unavailable_fallback,
        (),
        {"temperature": 0.1, "max_tokens": 20},
    ),
    "summarize": (
        "summarize",
        _summarize_fallback,
        (),
        {"temperature": 0.5, "max_tokens": 500},
    ),
    "fix-grammar": (
        "grammar",
        _grammar_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 1500},
    ),
    "paraphrase": (
        "paraphrase",
        _ai_unavailable_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 1500},
    ),
    # change-tone is handled dynamically
    "change-tone": (None, _ai_unavailable_fallback, (), {"max_tokens": 1500}),
    "analyze-sentiment": (
        "sentiment",
        _sentiment_fallback,
        (),
        {"temperature": 0.2, "max_tokens": 400},
    ),
    "lengthen-text": ("lengthen", _ai_unavailable_fallback, (), {"max_tokens": 2000}),
    "eli5": (
        "eli5",
        _ai_unavailable_fallback,
        (),
        {"temperature": 0.7, "max_tokens": 1500},
    ),
    "proofread": (
        "proofread",
        _ai_unavailable_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 2000},
    ),
    "generate-title": (
        "generate_title",
        _generate_title_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 300},
    ),
    "refactor-prompt": (
        "refactor_prompt",
        _ai_unavailable_fallback,
        (),
        {"temperature": 0.4, "max_tokens": 1500},
    ),
    # change-format is handled dynamically
    "change-format": (
        None,
        _format_fallback,
        (),
        {"temperature": 0.5, "max_tokens": 2000},
    ),
    # -- AI writing --
    "academic-style": (
        "academic_style",
        _passthrough_fallback,
        (),
        {"temperature": 0.5, "max_tokens": 1500},
    ),
    "creative-style": (
        "creative_style",
        _passthrough_fallback,
        (),
        {"temperature": 0.9, "max_tokens": 1500},
    ),
    "technical-style": (
        "technical_style",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 1500},
    ),
    "active-voice": (
        "active_voice",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 1500},
    ),
    "redundancy-remover": (
        "redundancy_remover",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 1500},
    ),
    "sentence-splitter": (
        "sentence_splitter",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 1500},
    ),
    "conciseness": (
        "conciseness",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 1500},
    ),
    "resume-bullets": (
        "resume_bullets",
        _passthrough_fallback,
        (),
        {"temperature": 0.6, "max_tokens": 500},
    ),
    "meeting-notes": (
        "meeting_notes",
        _passthrough_fallback,
        (),
        {"temperature": 0.4, "max_tokens": 800},
    ),
    "cover-letter": (
        "cover_letter",
        _passthrough_fallback,
        (),
        {"temperature": 0.7, "max_tokens": 800},
    ),
    "outline-to-draft": (
        "outline_to_draft",
        _passthrough_fallback,
        (),
        {"temperature": 0.7, "max_tokens": 1500},
    ),
    "continue-writing": (
        "continue_writing",
        _passthrough_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 800},
    ),
    "rewrite-unique": (
        "rewrite_unique",
        _passthrough_fallback,
        (),
        {"temperature": 0.9, "max_tokens": 1500},
    ),
    "tone-analyzer": (
        "tone_analyzer",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 400},
    ),
    # -- AI content --
    "linkedin-post": (
        "linkedin_post",
        _passthrough_fallback,
        (),
        {"temperature": 0.7, "max_tokens": 600},
    ),
    "twitter-thread": (
        "twitter_thread",
        _passthrough_fallback,
        (),
        {"temperature": 0.7, "max_tokens": 800},
    ),
    "instagram-caption": (
        "instagram_caption",
        _passthrough_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 600},
    ),
    "youtube-description": (
        "youtube_description",
        _passthrough_fallback,
        (),
        {"temperature": 0.6, "max_tokens": 600},
    ),
    "social-bio": (
        "social_bio",
        _passthrough_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 400},
    ),
    "product-description": (
        "product_description",
        _passthrough_fallback,
        (),
        {"temperature": 0.7, "max_tokens": 600},
    ),
    "cta-generator": (
        "cta_generator",
        _passthrough_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 400},
    ),
    "ad-copy": (
        "ad_copy",
        _passthrough_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 500},
    ),
    "landing-headline": (
        "landing_headline",
        _passthrough_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 300},
    ),
    "email-subject": (
        "email_subject",
        _passthrough_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 400},
    ),
    "content-ideas": (
        "content_ideas",
        _passthrough_fallback,
        (),
        {"temperature": 0.9, "max_tokens": 600},
    ),
    "hook-generator": (
        "hook_generator",
        _passthrough_fallback,
        (),
        {"temperature": 0.8, "max_tokens": 400},
    ),
    "angle-generator": (
        "angle_generator",
        _passthrough_fallback,
        (),
        {"temperature": 0.9, "max_tokens": 500},
    ),
    "faq-schema": (
        "faq_schema",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 800},
    ),
    # -- AI language --
    "pos-tagger": (
        "pos_tagger",
        _passthrough_fallback,
        (),
        {"temperature": 0.2, "max_tokens": 1500},
    ),
    "sentence-type": (
        "sentence_type",
        _passthrough_fallback,
        (),
        {"temperature": 0.2, "max_tokens": 800},
    ),
    "grammar-explain": (
        "grammar_explain",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 800},
    ),
    "synonym-finder": (
        "synonym_finder",
        _passthrough_fallback,
        (),
        {"temperature": 0.5, "max_tokens": 800},
    ),
    "antonym-finder": (
        "antonym_finder",
        _passthrough_fallback,
        (),
        {"temperature": 0.5, "max_tokens": 800},
    ),
    "define-words": (
        "define_words",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 800},
    ),
    "word-power": (
        "word_power",
        _passthrough_fallback,
        (),
        {"temperature": 0.6, "max_tokens": 1500},
    ),
    "vocab-complexity": (
        "vocab_complexity",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 600},
    ),
    "jargon-simplifier": (
        "jargon_simplifier",
        _passthrough_fallback,
        (),
        {"temperature": 0.4, "max_tokens": 1500},
    ),
    "formality-detector": (
        "formality_detector",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 400},
    ),
    "cliche-detector": (
        "cliche_detector",
        _passthrough_fallback,
        (),
        {"temperature": 0.5, "max_tokens": 600},
    ),
    # -- AI generators --
    "regex-generator": (
        "regex_generator",
        _passthrough_fallback,
        (),
        {"temperature": 0.3, "max_tokens": 400},
    ),
    "writing-prompt": (
        "writing_prompt",
        _passthrough_fallback,
        (),
        {"temperature": 0.9, "max_tokens": 400},
    ),
    "team-name-generator": (
        "team_name_generator",
        _passthrough_fallback,
        (),
        {"temperature": 0.9, "max_tokens": 300},
    ),
    "mock-api-response": (
        "mock_api_response",
        _passthrough_fallback,
        (),
        {"temperature": 0.6, "max_tokens": 800},
    ),
}


# ── Public dispatch function ──────────────────────────────────────────────────


async def run_ai_tool(
    tool_id: str,
    text: str,
    *extra_args: Any,
) -> str:
    """Run an AI tool by its *tool_id*.

    ``extra_args`` carries per-request dynamic values such as the target
    language for ``translate`` / ``transliterate``, the tone for
    ``change-tone``, or the format for ``change-format``.

    Raises ``KeyError`` if *tool_id* is not registered.
    """
    prompt_key, fallback_fn, default_extra, ai_kwargs = _AI_HANDLERS[tool_id]

    # Merge extra_args: request-time args override the static defaults
    merged_extra = extra_args if extra_args else default_extra

    # --- Dynamic prompt construction for parameterised tools -------------
    if tool_id == "translate" and extra_args:
        target_language = extra_args[0]
        prompt = (
            f"You are a translator. Translate the user's text into {target_language}. "
            "Preserve the original meaning, tone, and formatting as closely as possible. "
            "Return ONLY the translated text, nothing else. "
            "Do not include any notes or explanations."
        )
        return await _ai_transform(
            prompt, text, fallback_fn, *merged_extra, **ai_kwargs
        )

    if tool_id == "transliterate" and extra_args:
        target_language = extra_args[0]
        prompt = (
            f"You are a transliterator. Convert the user's text into {target_language} script "
            "(transliteration, NOT translation). Keep the original words and sounds -- "
            f"just write them using the {target_language} writing system. "
            "For example, English 'hello' in Hindi script becomes a phonetic rendering. "
            "Return ONLY the transliterated text, nothing else."
        )
        return await _ai_transform(
            prompt, text, fallback_fn, *merged_extra, **ai_kwargs
        )

    if tool_id == "change-tone" and extra_args:
        tone = extra_args[0]
        instruction = _TONE_INSTRUCTIONS.get(tone.lower(), _TONE_INSTRUCTIONS["formal"])
        prompt = (
            f"You are a tone changer. Given the user's text, {instruction} "
            "Preserve the original meaning completely. "
            "Return ONLY the rewritten text, nothing else."
        )
        return await _ai_transform(
            prompt, text, fallback_fn, *merged_extra, **ai_kwargs
        )

    if tool_id == "change-format" and extra_args:
        fmt = extra_args[0]
        base_prompt = _FORMAT_PROMPTS.get(fmt.lower(), _FORMAT_PROMPTS["paragraph"])
        prompt = (
            f"You are a text formatter. {base_prompt} "
            "Preserve ALL original information -- only change the structure/format. "
            "Return ONLY the reformatted text, nothing else."
        )
        return await _ai_transform(
            prompt, text, fallback_fn, *merged_extra, **ai_kwargs
        )

    # --- Standard (static-prompt) tools ---------------------------------
    if prompt_key is None:
        raise KeyError(
            f"Tool '{tool_id}' requires extra arguments but none were provided"
        )

    prompt = _PROMPTS[prompt_key]
    return await _ai_transform(prompt, text, fallback_fn, *merged_extra, **ai_kwargs)


async def stream_ai_tool(tool_id: str, text: str, *extra_args: Any):
    """Yield streaming token chunks for an AI tool via Server-Sent Events.

    Falls back to a single-chunk yield from ``run_ai_tool`` when Groq
    streaming is unavailable.
    """
    if not settings.GROQ_API_KEY or _groq_client is None:
        result = await run_ai_tool(tool_id, text, *extra_args)
        yield result
        return

    prompt_key, _fallback_fn, default_extra, ai_kwargs = _AI_HANDLERS[tool_id]
    merged_extra = extra_args if extra_args else default_extra

    # Build the prompt (same logic as run_ai_tool)
    if tool_id == "translate" and merged_extra:
        prompt = (
            f"You are a translator. Translate the user's text into {merged_extra[0]}. "
            "Preserve the original meaning, tone, and formatting. "
            "Return ONLY the translated text."
        )
    elif tool_id == "change-tone" and merged_extra:
        instruction = _TONE_INSTRUCTIONS.get(
            merged_extra[0].lower(), _TONE_INSTRUCTIONS["formal"]
        )
        prompt = (
            f"You are a tone changer. {instruction} Return ONLY the rewritten text."
        )
    elif tool_id == "change-format" and merged_extra:
        base = _FORMAT_PROMPTS.get(
            merged_extra[0].lower(), _FORMAT_PROMPTS["paragraph"]
        )
        prompt = f"You are a text formatter. {base} Return ONLY the reformatted text."
    elif prompt_key:
        prompt = _PROMPTS[prompt_key]
    else:
        result = await run_ai_tool(tool_id, text, *extra_args)
        yield result
        return

    temp = ai_kwargs.get("temperature", 0.7)
    max_tok = ai_kwargs.get("max_tokens", 200)
    async for token in _groq_chat_stream(prompt, text, temp, max_tok):
        yield token
