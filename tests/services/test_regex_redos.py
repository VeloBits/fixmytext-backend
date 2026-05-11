"""ReDoS protection: user-supplied regex patterns must time out cleanly.

Covers the FilterRequest / _line_matches path that is the only place in the
backend where a user-controlled pattern reaches a regex engine.
"""

import time

import pytest
import regex as _regex

from app.services.text_service import (
    USER_REGEX_TIMEOUT_S,
    RegexTimeoutError,
    filter_lines_contain,
    remove_lines_contain,
)

# Each payload is a (pattern, input) pair where the matcher is known to
# exhibit catastrophic backtracking on classic regex engines.
# Patterns that genuinely trip `regex.search(timeout=0.2)`.
#
# Note: the third-party `regex` library is smarter than stdlib `re` and will
# itself short-circuit some classic ReDoS patterns like (a+)+$ and (a*)*b
# without backtracking — those don't need the guard *and* don't exercise it.
# The patterns below use ambiguous alternation that the engine can't optimize
# away, so they actually exhaust the wall-clock budget.
#
# The line-length cap inside _line_matches is 2000 chars, so we sit just
# under it.
_LEN = 1900
REDOS_PAYLOADS = [
    (r"^(a|aa)+$", "a" * _LEN + "!"),
    (r"^(a|a?)+$", "a" * _LEN + "!"),
    (r"^(.*?,){50,}P$", ",".join(["x"] * 1000) + "Q"),
]


@pytest.mark.parametrize("pattern,payload", REDOS_PAYLOADS)
def test_filter_lines_redos_payload_raises_within_budget(pattern, payload):
    compiled = _regex.compile(pattern)
    start = time.monotonic()
    with pytest.raises(RegexTimeoutError):
        filter_lines_contain(
            payload, pattern, case_sensitive=True, use_regex=True, compiled=compiled
        )
    elapsed = time.monotonic() - start
    # Generous slack over the 200ms budget — we only care that we don't hang
    # for seconds. A real ReDoS without the guard runs for tens of seconds.
    assert elapsed < USER_REGEX_TIMEOUT_S * 5, (
        f"Timeout took {elapsed:.3f}s — guard not effective"
    )


@pytest.mark.parametrize("pattern,payload", REDOS_PAYLOADS)
def test_remove_lines_redos_payload_raises(pattern, payload):
    compiled = _regex.compile(pattern)
    with pytest.raises(RegexTimeoutError):
        remove_lines_contain(
            payload, pattern, case_sensitive=True, use_regex=True, compiled=compiled
        )


def test_safe_pattern_runs_normally():
    compiled = _regex.compile(r"hello")
    out = filter_lines_contain(
        "hello world\nfoo bar\nhello again",
        "hello",
        case_sensitive=True,
        use_regex=True,
        compiled=compiled,
    )
    assert out == "hello world\nhello again"


def test_no_compiled_pattern_returns_no_matches():
    # Defensive: when use_regex=True but compiled is None, _line_matches
    # returns False rather than crashing.
    out = filter_lines_contain(
        "anything", "x", case_sensitive=True, use_regex=True, compiled=None
    )
    assert out == ""
