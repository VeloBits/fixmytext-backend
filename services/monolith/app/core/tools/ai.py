"""AI tool registrations — all AI-powered text transformation tools."""

from app.core.tool_registry import ToolType, _register

A = ToolType.AI


def register() -> None:
    """Register all AI tools with the central registry."""

    # ── Core AI tools ──────────────────────────────────────────────────
    _register(
        "generate-hashtags", None, A, "Generate Hashtags", "ai", requires_auth=True
    )
    _register(
        "generate-seo-titles", None, A, "Generate SEO Titles", "ai", requires_auth=True
    )
    _register(
        "generate-meta-descriptions",
        None,
        A,
        "Generate Meta Descriptions",
        "ai",
        requires_auth=True,
    )
    _register(
        "generate-blog-outline",
        None,
        A,
        "Generate Blog Outline",
        "ai",
        requires_auth=True,
    )
    _register(
        "shorten-for-tweet", None, A, "Shorten for Tweet", "ai", requires_auth=True
    )
    _register("rewrite-email", None, A, "Rewrite Email", "ai", requires_auth=True)
    _register("extract-keywords", None, A, "Extract Keywords", "ai", requires_auth=True)
    _register(
        "translate",
        None,
        A,
        "Translate",
        "ai",
        requires_auth=True,
        request_model="TranslateRequest",
    )
    _register(
        "transliterate",
        None,
        A,
        "Transliterate",
        "ai",
        requires_auth=True,
        request_model="TranslateRequest",
    )
    _register("emojify", None, A, "Emojify", "ai", requires_auth=True)
    _register("detect-language", None, A, "Detect Language", "ai", requires_auth=True)
    _register("summarize", None, A, "Summarize", "ai", requires_auth=True)
    _register("fix-grammar", None, A, "Fix Grammar", "ai", requires_auth=True)
    _register("paraphrase", None, A, "Paraphrase", "ai", requires_auth=True)
    _register(
        "change-tone",
        None,
        A,
        "Change Tone",
        "ai",
        requires_auth=True,
        request_model="ToneRequest",
    )
    _register(
        "analyze-sentiment", None, A, "Analyze Sentiment", "ai", requires_auth=True
    )
    _register("lengthen-text", None, A, "Lengthen Text", "ai", requires_auth=True)
    _register("eli5", None, A, "ELI5", "ai", requires_auth=True)
    _register("proofread", None, A, "Proofread", "ai", requires_auth=True)
    _register("generate-title", None, A, "Generate Title", "ai", requires_auth=True)
    _register("refactor-prompt", None, A, "Refactor Prompt", "ai", requires_auth=True)
    _register(
        "change-format",
        None,
        A,
        "Change Format",
        "ai",
        requires_auth=True,
        request_model="FormatRequest",
    )

    # ── AI writing tools ───────────────────────────────────────────────
    _register(
        "academic-style", None, A, "Academic Style", "ai-writing", requires_auth=True
    )
    _register(
        "creative-style", None, A, "Creative Style", "ai-writing", requires_auth=True
    )
    _register(
        "technical-style", None, A, "Technical Style", "ai-writing", requires_auth=True
    )
    _register("active-voice", None, A, "Active Voice", "ai-writing", requires_auth=True)
    _register(
        "redundancy-remover",
        None,
        A,
        "Redundancy Remover",
        "ai-writing",
        requires_auth=True,
    )
    _register(
        "sentence-splitter",
        None,
        A,
        "Sentence Splitter",
        "ai-writing",
        requires_auth=True,
    )
    _register("conciseness", None, A, "Conciseness", "ai-writing", requires_auth=True)
    _register(
        "resume-bullets", None, A, "Resume Bullets", "ai-writing", requires_auth=True
    )
    _register(
        "meeting-notes", None, A, "Meeting Notes", "ai-writing", requires_auth=True
    )
    _register("cover-letter", None, A, "Cover Letter", "ai-writing", requires_auth=True)
    _register(
        "outline-to-draft",
        None,
        A,
        "Outline to Draft",
        "ai-writing",
        requires_auth=True,
    )
    _register(
        "continue-writing",
        None,
        A,
        "Continue Writing",
        "ai-writing",
        requires_auth=True,
    )
    _register(
        "rewrite-unique", None, A, "Rewrite Unique", "ai-writing", requires_auth=True
    )
    _register(
        "tone-analyzer", None, A, "Tone Analyzer", "ai-writing", requires_auth=True
    )

    # ── AI content tools ───────────────────────────────────────────────
    _register(
        "linkedin-post", None, A, "LinkedIn Post", "ai-content", requires_auth=True
    )
    _register(
        "twitter-thread", None, A, "Twitter Thread", "ai-content", requires_auth=True
    )
    _register(
        "instagram-caption",
        None,
        A,
        "Instagram Caption",
        "ai-content",
        requires_auth=True,
    )
    _register(
        "youtube-description",
        None,
        A,
        "YouTube Description",
        "ai-content",
        requires_auth=True,
    )
    _register("social-bio", None, A, "Social Bio", "ai-content", requires_auth=True)
    _register(
        "product-description",
        None,
        A,
        "Product Description",
        "ai-content",
        requires_auth=True,
    )
    _register(
        "cta-generator", None, A, "CTA Generator", "ai-content", requires_auth=True
    )
    _register("ad-copy", None, A, "Ad Copy", "ai-content", requires_auth=True)
    _register(
        "landing-headline",
        None,
        A,
        "Landing Headline",
        "ai-content",
        requires_auth=True,
    )
    _register(
        "email-subject", None, A, "Email Subject", "ai-content", requires_auth=True
    )
    _register(
        "content-ideas", None, A, "Content Ideas", "ai-content", requires_auth=True
    )
    _register(
        "hook-generator", None, A, "Hook Generator", "ai-content", requires_auth=True
    )
    _register(
        "angle-generator", None, A, "Angle Generator", "ai-content", requires_auth=True
    )
    _register("faq-schema", None, A, "FAQ Schema", "ai-content", requires_auth=True)

    # ── AI language tools ──────────────────────────────────────────────
    _register("pos-tagger", None, A, "POS Tagger", "ai-language", requires_auth=True)
    _register(
        "sentence-type", None, A, "Sentence Type", "ai-language", requires_auth=True
    )
    _register(
        "grammar-explain", None, A, "Grammar Explain", "ai-language", requires_auth=True
    )
    _register(
        "synonym-finder", None, A, "Synonym Finder", "ai-language", requires_auth=True
    )
    _register(
        "antonym-finder", None, A, "Antonym Finder", "ai-language", requires_auth=True
    )
    _register(
        "define-words", None, A, "Define Words", "ai-language", requires_auth=True
    )
    _register("word-power", None, A, "Word Power", "ai-language", requires_auth=True)
    _register(
        "vocab-complexity",
        None,
        A,
        "Vocab Complexity",
        "ai-language",
        requires_auth=True,
    )
    _register(
        "jargon-simplifier",
        None,
        A,
        "Jargon Simplifier",
        "ai-language",
        requires_auth=True,
    )
    _register(
        "formality-detector",
        None,
        A,
        "Formality Detector",
        "ai-language",
        requires_auth=True,
    )
    _register(
        "cliche-detector", None, A, "Cliche Detector", "ai-language", requires_auth=True
    )

    # ── AI generator tools ─────────────────────────────────────────────
    _register(
        "regex-generator",
        None,
        A,
        "Regex Generator",
        "ai-generator",
        requires_auth=True,
    )
    _register(
        "writing-prompt", None, A, "Writing Prompt", "ai-generator", requires_auth=True
    )
    _register(
        "team-name-generator",
        None,
        A,
        "Team Name Generator",
        "ai-generator",
        requires_auth=True,
    )
    _register(
        "mock-api-response",
        None,
        A,
        "Mock API Response",
        "ai-generator",
        requires_auth=True,
    )
