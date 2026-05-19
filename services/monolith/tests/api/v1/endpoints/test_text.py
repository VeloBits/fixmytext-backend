"""Tests for API endpoints: app/api/v1/endpoints/text.py"""

from unittest.mock import AsyncMock, patch

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────


_ALLOW = {"allowed": True, "reason": "free"}


@pytest.fixture(autouse=True)
def patch_access_checks():
    with (
        patch(
            "app.api.v1.endpoints.text.check_tool_access",
            AsyncMock(return_value=_ALLOW),
        ),
        patch(
            "app.api.v1.endpoints.text.check_visitor_access",
            AsyncMock(return_value=_ALLOW),
        ),
        patch("app.api.v1.endpoints.text.record_tool_discovery", AsyncMock()),
    ):
        yield


# ── Health check ──────────────────────────────────────────────────────────────


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Case transformation endpoints ─────────────────────────────────────────────


def test_uppercase(client):
    resp = client.post("/api/v1/text/uppercase", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "HELLO"


def test_lowercase(client):
    resp = client.post("/api/v1/text/lowercase", json={"text": "HELLO"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "hello"


def test_title_case(client):
    resp = client.post("/api/v1/text/titlecase", json={"text": "hello world"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "Hello World"


def test_sentence_case(client):
    resp = client.post("/api/v1/text/sentencecase", json={"text": "HELLO WORLD"})
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result[0].isupper()


def test_inverse_case(client):
    resp = client.post("/api/v1/text/inversecase", json={"text": "Hello"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "hELLO"


def test_lower_camel_case(client):
    resp = client.post("/api/v1/text/lower-camel-case", json={"text": "hello world"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "helloWorld"


def test_upper_camel_case(client):
    resp = client.post("/api/v1/text/upper-camel-case", json={"text": "hello world"})
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result[0].isupper()


def test_snake_case(client):
    resp = client.post("/api/v1/text/snake-case", json={"text": "Hello World"})
    assert resp.status_code == 200
    assert "_" in resp.json()["result"]


def test_kebab_case(client):
    resp = client.post("/api/v1/text/kebab-case", json={"text": "Hello World"})
    assert resp.status_code == 200
    assert "-" in resp.json()["result"]


def test_alternating_case(client):
    resp = client.post("/api/v1/text/alternating-case", json={"text": "hello"})
    assert resp.status_code == 200


def test_wide_text(client):
    resp = client.post("/api/v1/text/wide-text", json={"text": "hi"})
    assert resp.status_code == 200
    assert " " in resp.json()["result"]


def test_dot_case(client):
    resp = client.post("/api/v1/text/dot-case", json={"text": "Hello World"})
    assert resp.status_code == 200


def test_constant_case(client):
    resp = client.post("/api/v1/text/constant-case", json={"text": "Hello World"})
    assert resp.status_code == 200


def test_train_case(client):
    resp = client.post("/api/v1/text/train-case", json={"text": "hello world"})
    assert resp.status_code == 200


# ── Space/whitespace endpoints ────────────────────────────────────────────────


def test_remove_extra_spaces(client):
    resp = client.post(
        "/api/v1/text/remove-extra-spaces", json={"text": "  hello   world  "}
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "hello world"


def test_remove_all_spaces(client):
    resp = client.post("/api/v1/text/remove-all-spaces", json={"text": "hello world"})
    assert resp.status_code == 200
    assert " " not in resp.json()["result"]


def test_remove_line_breaks(client):
    resp = client.post("/api/v1/text/remove-line-breaks", json={"text": "line1\nline2"})
    assert resp.status_code == 200
    assert "\n" not in resp.json()["result"]


def test_trim_lines(client):
    resp = client.post("/api/v1/text/trim-lines", json={"text": "  hello  \n  world  "})
    assert resp.status_code == 200


def test_strip_empty_lines(client):
    resp = client.post("/api/v1/text/strip-empty-lines", json={"text": "a\n\nb\n\nc"})
    assert resp.status_code == 200


# ── Encoding endpoints ────────────────────────────────────────────────────────


def test_base64_encode(client):
    resp = client.post("/api/v1/text/base64-encode", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "aGVsbG8="


def test_base64_decode(client):
    resp = client.post("/api/v1/text/base64-decode", json={"text": "aGVsbG8="})
    assert resp.status_code == 200
    assert resp.json()["result"] == "hello"


def test_url_encode(client):
    resp = client.post("/api/v1/text/url-encode", json={"text": "hello world"})
    assert resp.status_code == 200
    assert " " not in resp.json()["result"]


def test_url_decode(client):
    resp = client.post("/api/v1/text/url-decode", json={"text": "hello%20world"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "hello world"


def test_html_escape(client):
    resp = client.post("/api/v1/text/html-escape", json={"text": "<p>hi</p>"})
    assert resp.status_code == 200
    assert "&lt;" in resp.json()["result"]


def test_html_unescape(client):
    resp = client.post(
        "/api/v1/text/html-unescape", json={"text": "&lt;p&gt;hi&lt;/p&gt;"}
    )
    assert resp.status_code == 200
    assert "<p>" in resp.json()["result"]


def test_hex_encode(client):
    resp = client.post("/api/v1/text/hex-encode", json={"text": "hi"})
    assert resp.status_code == 200


def test_binary_encode(client):
    resp = client.post("/api/v1/text/binary-encode", json={"text": "A"})
    assert resp.status_code == 200
    assert "01000001" in resp.json()["result"]


def test_morse_encode(client):
    resp = client.post("/api/v1/text/morse-encode", json={"text": "SOS"})
    assert resp.status_code == 200


def test_rot13(client):
    resp = client.post("/api/v1/text/rot13", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "uryyb"


# ── Text manipulation endpoints ───────────────────────────────────────────────


def test_reverse(client):
    resp = client.post("/api/v1/text/reverse", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "olleh"


def test_reverse_lines(client):
    resp = client.post("/api/v1/text/reverse-lines", json={"text": "a\nb\nc"})
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result.split("\n")[0] == "c"


def test_sort_lines_asc(client):
    resp = client.post(
        "/api/v1/text/sort-lines-asc", json={"text": "banana\napple\ncherry"}
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "apple\nbanana\ncherry"


def test_sort_lines_desc(client):
    resp = client.post(
        "/api/v1/text/sort-lines-desc", json={"text": "apple\nbanana\ncherry"}
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "cherry\nbanana\napple"


def test_remove_duplicate_lines(client):
    resp = client.post(
        "/api/v1/text/remove-duplicate-lines", json={"text": "a\nb\na\nc"}
    )
    assert resp.status_code == 200


def test_strip_html(client):
    resp = client.post("/api/v1/text/strip-html", json={"text": "<p>Hello</p>"})
    assert resp.status_code == 200
    assert "<" not in resp.json()["result"]


def test_number_lines(client):
    resp = client.post("/api/v1/text/number-lines", json={"text": "first\nsecond"})
    assert resp.status_code == 200
    assert "1" in resp.json()["result"]


def test_caesar_cipher(client):
    resp = client.post("/api/v1/text/caesar-cipher", json={"text": "hello", "shift": 3})
    assert resp.status_code == 200
    assert resp.json()["result"] == "khoor"


def test_truncate_lines(client):
    resp = client.post(
        "/api/v1/text/truncate-lines", json={"text": "Hello World", "max_length": 5}
    )
    assert resp.status_code == 200


def test_atbash(client):
    resp = client.post("/api/v1/text/atbash", json={"text": "abc"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "zyx"


# ── Validation ────────────────────────────────────────────────────────────────


def test_empty_text_returns_422(client):
    resp = client.post("/api/v1/text/uppercase", json={"text": ""})
    assert resp.status_code == 422


def test_missing_text_returns_422(client):
    resp = client.post("/api/v1/text/uppercase", json={})
    assert resp.status_code == 422


def test_response_has_original(client):
    resp = client.post("/api/v1/text/uppercase", json={"text": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["original"] == "hello"
    assert data["operation"] == "uppercase"


# ── AI endpoints require auth ─────────────────────────────────────────────────


def test_fix_grammar_requires_auth(unauth_client):
    resp = unauth_client.post(
        "/api/v1/text/fix-grammar", json={"text": "i am go to school"}
    )
    assert resp.status_code == 401


def test_summarize_requires_auth(unauth_client):
    resp = unauth_client.post("/api/v1/text/summarize", json={"text": "long text here"})
    assert resp.status_code == 401


def test_translate_requires_auth(unauth_client):
    resp = unauth_client.post(
        "/api/v1/text/translate", json={"text": "hello", "target_language": "Spanish"}
    )
    assert resp.status_code == 401


def test_change_tone_requires_auth(unauth_client):
    resp = unauth_client.post(
        "/api/v1/text/change-tone", json={"text": "hello", "tone": "formal"}
    )
    assert resp.status_code == 401


def test_paraphrase_requires_auth(unauth_client):
    resp = unauth_client.post("/api/v1/text/paraphrase", json={"text": "hello world"})
    assert resp.status_code == 401


# ── AI endpoints succeed when mocked ─────────────────────────────────────────


def test_fix_grammar_with_mock_ai(client):
    with patch(
        "app.services.ai_service.run_ai_tool",
        AsyncMock(return_value="Fixed text."),
    ):
        resp = client.post(
            "/api/v1/text/fix-grammar", json={"text": "i am go to school"}
        )
    assert resp.status_code == 200
    assert resp.json()["result"] == "Fixed text."


def test_summarize_with_mock_ai(client):
    with patch(
        "app.services.ai_service.run_ai_tool",
        AsyncMock(return_value="Summary."),
    ):
        resp = client.post(
            "/api/v1/text/summarize", json={"text": "A very long piece of text."}
        )
    assert resp.status_code == 200


def test_translate_with_mock_ai(client):
    with patch(
        "app.services.ai_service.run_ai_tool",
        AsyncMock(return_value="Hola"),
    ):
        resp = client.post(
            "/api/v1/text/translate",
            json={"text": "hello", "target_language": "Spanish"},
        )
    assert resp.status_code == 200


def test_change_tone_with_mock_ai(client):
    with patch(
        "app.services.ai_service.run_ai_tool",
        AsyncMock(return_value="Formal text."),
    ):
        resp = client.post(
            "/api/v1/text/change-tone",
            json={"text": "hey what's up", "tone": "formal"},
        )
    assert resp.status_code == 200


def test_change_tone_invalid_tone(client):
    resp = client.post(
        "/api/v1/text/change-tone",
        json={"text": "hello", "tone": "not_valid_tone"},
    )
    assert resp.status_code == 422


def test_change_format_invalid_format(client):
    resp = client.post(
        "/api/v1/text/change-format",
        json={"text": "hello", "format": "not_valid_format"},
    )
    assert resp.status_code == 422


# ── Access denied → 429 ───────────────────────────────────────────────────────


def test_text_endpoint_access_denied_returns_429(client, mock_db):
    with (
        patch(
            "app.api.v1.endpoints.text.check_tool_access",
            AsyncMock(
                return_value={"allowed": False, "message": "Daily limit reached"}
            ),
        ),
        patch(
            "app.api.v1.endpoints.text.check_visitor_access",
            AsyncMock(
                return_value={"allowed": False, "message": "Daily limit reached"}
            ),
        ),
    ):
        resp = client.post("/api/v1/text/uppercase", json={"text": "hello"})
    assert resp.status_code == 429


# ── Additional local endpoints ────────────────────────────────────────────────


def test_strip_emoji(client):
    resp = client.post("/api/v1/text/strip-emoji", json={"text": "hello 😀 world"})
    assert resp.status_code == 200


def test_normalize_whitespace(client):
    resp = client.post(
        "/api/v1/text/normalize-whitespace", json={"text": "  hello  \t world  "}
    )
    assert resp.status_code == 200


def test_remove_accents(client):
    resp = client.post("/api/v1/text/remove-accents", json={"text": "café"})
    assert resp.status_code == 200


def test_format_json(client):
    resp = client.post("/api/v1/text/format-json", json={"text": '{"a": 1}'})
    assert resp.status_code == 200


def test_atbash_endpoint(client):
    resp = client.post("/api/v1/text/atbash", json={"text": "hello"})
    assert resp.status_code == 200


def test_rot13_endpoint(client):
    resp = client.post("/api/v1/text/rot13", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "uryyb"
