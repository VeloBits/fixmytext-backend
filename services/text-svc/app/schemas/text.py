"""Pydantic models (schemas) for text-processing requests and responses.

Contains only the schemas used by LOCAL tools.  AI-tool schemas
(ToneRequest, TranslateRequest, FormatRequest) live in ai-svc.
"""

from typing import Any, Literal

import regex as _regex
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NonBlankTextMixin(BaseModel):
    """Reject ``text`` that is empty after stripping whitespace.

    Whitespace-only input satisfies ``min_length=1`` but produces a useless
    transform - and validation must fail here, at request-parse time, so the
    entitlement gate never consumes a free use for it. The text itself is NOT
    trimmed: leading/trailing whitespace is meaningful input for several tools.
    """

    @field_validator("text", check_fields=False)
    @classmethod
    def _reject_blank_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Text must contain at least one non-whitespace character.")
        return v


class TextRequest(NonBlankTextMixin):
    """Payload sent by the client for any text transformation."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
        examples=["Hello World"],
    )


class SplitJoinRequest(NonBlankTextMixin):
    """Payload for split-to-lines and join-lines requests."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    delimiter: str = Field(
        default=",",
        max_length=20,
        description="Delimiter or separator character(s).",
    )


class PadRequest(NonBlankTextMixin):
    """Payload for pad-lines requests."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    align: Literal["left", "right", "center"] = Field(
        default="left",
        description="Alignment direction: left, right, or center.",
    )


class WrapRequest(NonBlankTextMixin):
    """Payload for wrap-lines requests."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    prefix: str = Field(
        default="",
        max_length=100,
        description="Text to prepend to each line.",
    )
    suffix: str = Field(
        default="",
        max_length=100,
        description="Text to append to each line.",
    )


class FilterRequest(NonBlankTextMixin):
    """Payload for filter-lines and remove-lines requests."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    pattern: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Word or phrase (or regex pattern) to match against each line.",
    )
    case_sensitive: bool = Field(
        default=False,
        description="If true, match is case-sensitive.",
    )
    use_regex: bool = Field(
        default=False,
        description="If true, treat pattern as a regular expression.",
    )
    # Pre-compiled pattern - populated by the validator below; excluded from
    # serialisation so it never appears in API responses or OpenAPI schema.
    # Typed as Any to accommodate the `regex` library's Pattern type while
    # keeping Pydantic's schema generation happy.
    compiled_pattern: Any = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _compile_regex(self) -> "FilterRequest":
        """Compile and validate the regex pattern eagerly at request-parse time.

        Uses the third-party `regex` library so that .search() supports a
        per-call `timeout` argument - the runtime ReDoS guard lives in
        text_service._line_matches.
        """
        if self.use_regex:
            flags = 0 if self.case_sensitive else _regex.IGNORECASE
            try:
                self.compiled_pattern = _regex.compile(self.pattern, flags)
            except _regex.error as exc:
                raise ValueError(f"Invalid regular expression: {exc}") from exc
        return self


class TruncateRequest(NonBlankTextMixin):
    """Payload for truncate-lines requests."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    max_length: int = Field(
        default=80,
        ge=5,
        le=1000,
        description="Maximum character length per line.",
    )


class NthLineRequest(NonBlankTextMixin):
    """Payload for extract-nth-lines requests."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    n: int = Field(
        default=2,
        ge=2,
        le=100,
        description="Extract every Nth line.",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Starting line offset (0-indexed).",
    )


class CaesarRequest(NonBlankTextMixin):
    """Payload for Caesar cipher requests."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    shift: int = Field(
        default=3,
        ge=1,
        le=25,
        description="Number of positions to shift each letter.",
    )


class RailFenceRequest(NonBlankTextMixin):
    """Payload for Rail Fence cipher requests."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    rails: int = Field(
        default=3,
        ge=2,
        le=10,
        description="Number of rails for the cipher.",
    )


class KeyedCipherRequest(NonBlankTextMixin):
    """Payload for cipher requests that require a key (Vigenere, Playfair, etc.)."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="The cipher key or passphrase.",
    )


class SubstitutionRequest(NonBlankTextMixin):
    """Payload for substitution cipher requests."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The input text to be processed.",
    )
    mapping: str = Field(
        ...,
        min_length=26,
        max_length=26,
        description="26-character substitution alphabet (A-Z mapping).",
    )


class TextResponse(BaseModel):
    """Transformed text returned by the API."""

    original: str = Field(..., description="The original input text.")
    result: str = Field(..., description="The transformed output text.")
    operation: str = Field(..., description="Name of the operation performed.")
