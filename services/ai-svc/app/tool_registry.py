"""
AI-only tool registry for ai-svc.

A slim standalone version of the monolith's tool_registry — contains only
AI tools.  The monolith's LOCAL tools are intentionally excluded; this
service only handles Groq-backed AI transformations.

Adding a new AI tool: add a ``_register(...)`` call below and a matching
entry in ``app/services/ai_service.py``'s ``_AI_HANDLERS`` dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


class ToolType(StrEnum):
    """Tool execution backend type."""

    AI = "ai"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Immutable definition of a single AI text transformation tool.

    Attributes:
        id: URL-safe slug used as the route path parameter.
        tool_type: Always ``ToolType.AI`` in this registry.
        display_name: Human-readable label for OpenAPI docs.
        category: Grouping tag for the OpenAPI sidebar.
        requires_auth: All AI tools require authentication.
    """

    id: str
    tool_type: ToolType
    display_name: str
    category: str
    requires_auth: bool = True


# ---------------------------------------------------------------------------
# Internal registry dict — populated at import time
# ---------------------------------------------------------------------------

_AI_TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def get_tool(tool_id: str) -> ToolDefinition | None:
    """Look up a tool by ID.  Returns ``None`` if not found."""
    return _AI_TOOL_REGISTRY.get(tool_id)


def get_all_tools() -> list[ToolDefinition]:
    """Return all registered AI tools."""
    return list(_AI_TOOL_REGISTRY.values())


def _register(tool_id: str, display_name: str, category: str) -> None:
    """Register an AI tool.  Called at module-init time only."""
    _AI_TOOL_REGISTRY[tool_id] = ToolDefinition(
        id=tool_id,
        tool_type=ToolType.AI,
        display_name=display_name,
        category=category,
        requires_auth=True,
    )


# ---------------------------------------------------------------------------
# Registration of all AI tools
# (mirrors app.core.tools.ai in the monolith)
# ---------------------------------------------------------------------------

# ── Core AI tools ──────────────────────────────────────────────────────────
_register("generate-hashtags", "Generate Hashtags", "ai")
_register("generate-seo-titles", "Generate SEO Titles", "ai")
_register("generate-meta-descriptions", "Generate Meta Descriptions", "ai")
_register("generate-blog-outline", "Generate Blog Outline", "ai")
_register("shorten-for-tweet", "Shorten for Tweet", "ai")
_register("rewrite-email", "Rewrite Email", "ai")
_register("extract-keywords", "Extract Keywords", "ai")
_register("translate", "Translate", "ai")
_register("transliterate", "Transliterate", "ai")
_register("emojify", "Emojify", "ai")
_register("detect-language", "Detect Language", "ai")
_register("summarize", "Summarize", "ai")
_register("fix-grammar", "Fix Grammar", "ai")
_register("paraphrase", "Paraphrase", "ai")
_register("change-tone", "Change Tone", "ai")
_register("analyze-sentiment", "Analyze Sentiment", "ai")
_register("lengthen-text", "Lengthen Text", "ai")
_register("eli5", "ELI5", "ai")
_register("proofread", "Proofread", "ai")
_register("generate-title", "Generate Title", "ai")
_register("refactor-prompt", "Refactor Prompt", "ai")
_register("change-format", "Change Format", "ai")

# ── AI writing tools ───────────────────────────────────────────────────────
_register("academic-style", "Academic Style", "ai-writing")
_register("creative-style", "Creative Style", "ai-writing")
_register("technical-style", "Technical Style", "ai-writing")
_register("active-voice", "Active Voice", "ai-writing")
_register("redundancy-remover", "Redundancy Remover", "ai-writing")
_register("sentence-splitter", "Sentence Splitter", "ai-writing")
_register("conciseness", "Conciseness", "ai-writing")
_register("resume-bullets", "Resume Bullets", "ai-writing")
_register("meeting-notes", "Meeting Notes", "ai-writing")
_register("cover-letter", "Cover Letter", "ai-writing")
_register("outline-to-draft", "Outline to Draft", "ai-writing")
_register("continue-writing", "Continue Writing", "ai-writing")
_register("rewrite-unique", "Rewrite Unique", "ai-writing")
_register("tone-analyzer", "Tone Analyzer", "ai-writing")

# ── AI content tools ───────────────────────────────────────────────────────
_register("linkedin-post", "LinkedIn Post", "ai-content")
_register("twitter-thread", "Twitter Thread", "ai-content")
_register("instagram-caption", "Instagram Caption", "ai-content")
_register("youtube-description", "YouTube Description", "ai-content")
_register("social-bio", "Social Bio", "ai-content")
_register("product-description", "Product Description", "ai-content")
_register("cta-generator", "CTA Generator", "ai-content")
_register("ad-copy", "Ad Copy", "ai-content")
_register("landing-headline", "Landing Headline", "ai-content")
_register("email-subject", "Email Subject", "ai-content")
_register("content-ideas", "Content Ideas", "ai-content")
_register("hook-generator", "Hook Generator", "ai-content")
_register("angle-generator", "Angle Generator", "ai-content")
_register("faq-schema", "FAQ Schema", "ai-content")

# ── AI language tools ──────────────────────────────────────────────────────
_register("pos-tagger", "POS Tagger", "ai-language")
_register("sentence-type", "Sentence Type", "ai-language")
_register("grammar-explain", "Grammar Explain", "ai-language")
_register("synonym-finder", "Synonym Finder", "ai-language")
_register("antonym-finder", "Antonym Finder", "ai-language")
_register("define-words", "Define Words", "ai-language")
_register("word-power", "Word Power", "ai-language")
_register("vocab-complexity", "Vocab Complexity", "ai-language")
_register("jargon-simplifier", "Jargon Simplifier", "ai-language")
_register("formality-detector", "Formality Detector", "ai-language")
_register("cliche-detector", "Cliche Detector", "ai-language")

# ── AI generator tools ─────────────────────────────────────────────────────
_register("regex-generator", "Regex Generator", "ai-generator")
_register("writing-prompt", "Writing Prompt", "ai-generator")
_register("team-name-generator", "Team Name Generator", "ai-generator")
_register("mock-api-response", "Mock API Response", "ai-generator")
