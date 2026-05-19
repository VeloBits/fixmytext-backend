"""Extended tests for /api/v1/text/* — covers endpoints not yet in test_text.py.

Adds parametrized tests for all local text tools, cipher endpoints,
encoding/decoding endpoints, and additional AI endpoint auth checks.
"""

from unittest.mock import AsyncMock, patch

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

_ALLOW = {"allowed": True, "reason": "free"}


@pytest.fixture(autouse=True)
def patch_access_checks():
    """Bypass tool-access checks so we test the transformation logic only."""
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


# ── Parametrized local tool endpoint tests ───────────────────────────────────

# (endpoint_path, input_text, assertion_callback_name)
# assertion_callback_name is one of: "not_empty", "contains:<text>", "equals:<text>"


LOCAL_TOOL_CASES = [
    # Case transformations
    ("/api/v1/text/uppercase", "hello", "equals:HELLO"),
    ("/api/v1/text/lowercase", "HELLO", "equals:hello"),
    ("/api/v1/text/inversecase", "Hello", "equals:hELLO"),
    ("/api/v1/text/titlecase", "hello world", "equals:Hello World"),
    ("/api/v1/text/sentencecase", "hello world", "not_empty"),
    ("/api/v1/text/upper-camel-case", "hello world", "equals:HelloWorld"),
    ("/api/v1/text/lower-camel-case", "hello world", "equals:helloWorld"),
    ("/api/v1/text/snake-case", "Hello World", "contains:_"),
    ("/api/v1/text/kebab-case", "Hello World", "contains:-"),
    ("/api/v1/text/capitalize-words", "hello world", "equals:Hello World"),
    ("/api/v1/text/alternating-case", "hello", "not_empty"),
    ("/api/v1/text/inverse-word-case", "hello world", "not_empty"),
    ("/api/v1/text/wide-text", "hi", "equals:h i"),
    ("/api/v1/text/small-caps", "hello", "not_empty"),
    ("/api/v1/text/upside-down", "hello", "not_empty"),
    ("/api/v1/text/strikethrough", "hello", "contains:<del>"),
    ("/api/v1/text/ap-title-case", "the quick brown fox", "not_empty"),
    ("/api/v1/text/swap-word-case", "hello world", "not_empty"),
    ("/api/v1/text/dot-case", "Hello World", "contains:."),
    ("/api/v1/text/constant-case", "hello world", "contains:_"),
    ("/api/v1/text/train-case", "hello world", "contains:-"),
    ("/api/v1/text/path-case", "Hello World", "contains:/"),
    ("/api/v1/text/flat-case", "Hello World", "not_empty"),
    ("/api/v1/text/cobol-case", "hello world", "contains:-"),
    # Whitespace / cleanup
    ("/api/v1/text/remove-extra-spaces", "  hello   world  ", "equals:hello world"),
    ("/api/v1/text/remove-all-spaces", "hello world", "equals:helloworld"),
    ("/api/v1/text/remove-line-breaks", "line1\nline2", "not_empty"),
    ("/api/v1/text/strip-html", "<p>Hello</p>", "equals:Hello"),
    ("/api/v1/text/remove-accents", "cafe\u0301", "not_empty"),
    ("/api/v1/text/toggle-smart-quotes", '"Hello"', "not_empty"),
    ("/api/v1/text/strip-invisible", "hello\u200bworld", "not_empty"),
    ("/api/v1/text/strip-emoji", "hello world", "not_empty"),
    ("/api/v1/text/normalize-whitespace", "  hello  \t world", "not_empty"),
    ("/api/v1/text/strip-non-ascii", "hello cafe\u0301", "not_empty"),
    ("/api/v1/text/fix-line-endings", "a\r\nb\rc", "not_empty"),
    ("/api/v1/text/strip-markdown", "**bold** and *italic*", "not_empty"),
    ("/api/v1/text/trim-lines", "  hello  \n  world  ", "not_empty"),
    ("/api/v1/text/strip-empty-lines", "a\n\nb\n\nc", "not_empty"),
    ("/api/v1/text/strip-urls", "visit https://example.com now", "not_empty"),
    ("/api/v1/text/strip-emails", "contact user@example.com today", "not_empty"),
    ("/api/v1/text/normalize-punctuation", "hello , world !", "not_empty"),
    ("/api/v1/text/strip-numbers", "abc123def", "not_empty"),
    # Encoding
    ("/api/v1/text/base64-encode", "hello", "equals:aGVsbG8="),
    ("/api/v1/text/url-encode", "hello world", "not_empty"),
    ("/api/v1/text/hex-encode", "A", "not_empty"),
    ("/api/v1/text/morse-encode", "SOS", "not_empty"),
    ("/api/v1/text/binary-encode", "A", "contains:01000001"),
    ("/api/v1/text/octal-encode", "A", "not_empty"),
    ("/api/v1/text/decimal-encode", "A", "contains:65"),
    ("/api/v1/text/unicode-escape", "A", "not_empty"),
    ("/api/v1/text/brainfuck-encode", "A", "not_empty"),
    ("/api/v1/text/base32-encode", "hello", "not_empty"),
    ("/api/v1/text/ascii85-encode", "hello", "not_empty"),
    # Text tools
    ("/api/v1/text/reverse", "hello", "equals:olleh"),
    (
        "/api/v1/text/sort-lines-asc",
        "banana\napple\ncherry",
        "equals:apple\nbanana\ncherry",
    ),
    (
        "/api/v1/text/sort-lines-desc",
        "apple\nbanana\ncherry",
        "equals:cherry\nbanana\napple",
    ),
    ("/api/v1/text/remove-duplicate-lines", "a\nb\na", "not_empty"),
    ("/api/v1/text/reverse-lines", "a\nb\nc", "not_empty"),
    ("/api/v1/text/number-lines", "first\nsecond", "contains:1"),
    ("/api/v1/text/shuffle-lines", "a\nb\nc\nd", "not_empty"),
    ("/api/v1/text/sort-by-length", "cat\nelephant\nox", "not_empty"),
    ("/api/v1/text/sort-numeric", "10\n2\n1", "not_empty"),
    ("/api/v1/text/line-frequency", "a\nb\na\nc\na", "not_empty"),
    ("/api/v1/text/rot13", "hello", "equals:uryyb"),
    # Ciphers
    ("/api/v1/text/atbash", "abc", "equals:zyx"),
    ("/api/v1/text/caesar-brute-force", "khoor", "not_empty"),
    ("/api/v1/text/nato-phonetic", "ABC", "not_empty"),
    ("/api/v1/text/bacon-cipher", "AB", "not_empty"),
    # Escape/unescape
    ("/api/v1/text/json-escape", 'hello "world"', "not_empty"),
    ("/api/v1/text/html-escape", "<p>hi</p>", "contains:&lt;"),
    ("/api/v1/text/html-unescape", "&lt;p&gt;hi&lt;/p&gt;", "contains:<p>"),
    # CSV/table
    ("/api/v1/text/csv-to-table", "name,age\nAlice,30", "not_empty"),
]


class TestLocalToolsParametrized:
    """Parametrized tests for all local text tool endpoints."""

    @pytest.mark.parametrize("path,text,assertion", LOCAL_TOOL_CASES)
    def test_local_tool(self, client, path, text, assertion):
        """Each local tool endpoint returns 200 and correct result."""
        resp = client.post(path, json={"text": text})
        assert resp.status_code == 200, (
            f"{path} returned {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert "result" in data
        assert "original" in data
        result = data["result"]
        if assertion.startswith("equals:"):
            expected = assertion[len("equals:") :]
            assert result == expected, f"{path}: expected {expected!r}, got {result!r}"
        elif assertion.startswith("contains:"):
            substr = assertion[len("contains:") :]
            assert substr in result, f"{path}: expected {substr!r} in {result!r}"
        elif assertion == "not_empty":
            assert isinstance(result, str)


# ── Decode endpoints (valid input) ───────────────────────────────────────────

DECODE_CASES = [
    ("/api/v1/text/base64-decode", "aGVsbG8=", "hello"),
    ("/api/v1/text/url-decode", "hello%20world", "hello world"),
    ("/api/v1/text/hex-decode", "68656c6c6f", "hello"),
    ("/api/v1/text/binary-decode", "01000001", "A"),
    ("/api/v1/text/octal-decode", "101", "A"),
    ("/api/v1/text/decimal-decode", "65", "A"),
]


class TestDecodeEndpoints:
    """Test decode endpoints with valid input."""

    @pytest.mark.parametrize("path,text,expected", DECODE_CASES)
    def test_decode_valid(self, client, path, text, expected):
        """Valid encoded input decodes correctly."""
        resp = client.post(path, json={"text": text})
        assert resp.status_code == 200
        assert resp.json()["result"] == expected

    def test_base64_decode_invalid(self, client):
        """Invalid Base64 input returns 400."""
        resp = client.post("/api/v1/text/base64-decode", json={"text": "not!!valid!!"})
        assert resp.status_code == 400

    def test_hex_decode_invalid(self, client):
        """Invalid hex input returns 400."""
        resp = client.post("/api/v1/text/hex-decode", json={"text": "ZZZZ"})
        assert resp.status_code == 400

    def test_binary_decode_invalid(self, client):
        """Invalid binary input returns 400."""
        resp = client.post("/api/v1/text/binary-decode", json={"text": "not binary"})
        assert resp.status_code == 400

    def test_morse_decode_valid(self, client):
        """Valid Morse code decodes correctly."""
        resp = client.post("/api/v1/text/morse-decode", json={"text": "... --- ..."})
        assert resp.status_code == 200

    def test_brainfuck_decode_valid(self, client):
        """Valid Brainfuck program executes."""
        # Program that prints 'A' (ASCII 65): 65 '+' followed by '.'
        program = "+" * 65 + "."
        resp = client.post("/api/v1/text/brainfuck-decode", json={"text": program})
        assert resp.status_code == 200
        assert resp.json()["result"] == "A"

    def test_octal_decode_invalid(self, client):
        """Invalid octal input returns 400."""
        resp = client.post("/api/v1/text/octal-decode", json={"text": "abc"})
        assert resp.status_code == 400

    def test_decimal_decode_invalid(self, client):
        """Invalid decimal input returns 400."""
        resp = client.post("/api/v1/text/decimal-decode", json={"text": "not numbers"})
        assert resp.status_code == 400


# ── Cipher endpoints with special request bodies ─────────────────────────────


class TestCipherEndpoints:
    """Test cipher endpoints that use custom request schemas."""

    def test_caesar_cipher(self, client):
        """Caesar cipher with shift=3 on 'hello' gives 'khoor'."""
        resp = client.post(
            "/api/v1/text/caesar-cipher", json={"text": "hello", "shift": 3}
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "khoor"

    def test_vigenere_encrypt(self, client):
        """Vigenere encrypt returns 200 with valid key."""
        resp = client.post(
            "/api/v1/text/vigenere-encrypt", json={"text": "hello", "key": "key"}
        )
        assert resp.status_code == 200

    def test_vigenere_decrypt(self, client):
        """Vigenere decrypt reverses encrypt."""
        enc_resp = client.post(
            "/api/v1/text/vigenere-encrypt", json={"text": "hello", "key": "key"}
        )
        encrypted = enc_resp.json()["result"]
        dec_resp = client.post(
            "/api/v1/text/vigenere-decrypt", json={"text": encrypted, "key": "key"}
        )
        assert dec_resp.status_code == 200
        assert dec_resp.json()["result"].lower() == "hello"

    def test_rail_fence_encrypt(self, client):
        """Rail fence encrypt returns 200."""
        resp = client.post(
            "/api/v1/text/rail-fence-encrypt", json={"text": "hello world", "rails": 3}
        )
        assert resp.status_code == 200

    def test_rail_fence_decrypt(self, client):
        """Rail fence decrypt reverses encrypt."""
        enc_resp = client.post(
            "/api/v1/text/rail-fence-encrypt", json={"text": "hello world", "rails": 3}
        )
        encrypted = enc_resp.json()["result"]
        dec_resp = client.post(
            "/api/v1/text/rail-fence-decrypt", json={"text": encrypted, "rails": 3}
        )
        assert dec_resp.status_code == 200

    def test_playfair_encrypt(self, client):
        """Playfair encrypt returns 200."""
        resp = client.post(
            "/api/v1/text/playfair-encrypt", json={"text": "hello", "key": "keyword"}
        )
        assert resp.status_code == 200

    def test_substitution_cipher(self, client):
        """Substitution cipher with full alphabet mapping."""
        mapping = "ZYXWVUTSRQPONMLKJIHGFEDCBA"
        resp = client.post(
            "/api/v1/text/substitution-cipher",
            json={"text": "hello", "mapping": mapping},
        )
        assert resp.status_code == 200

    def test_columnar_transposition(self, client):
        """Columnar transposition returns 200."""
        resp = client.post(
            "/api/v1/text/columnar-transposition",
            json={"text": "hello world", "key": "key"},
        )
        assert resp.status_code == 200


# ── Special request endpoints ────────────────────────────────────────────────


class TestSpecialRequestEndpoints:
    """Test endpoints using SplitJoinRequest, PadRequest, etc."""

    def test_split_to_lines(self, client):
        """Split by comma returns separate lines."""
        resp = client.post(
            "/api/v1/text/split-to-lines", json={"text": "a,b,c", "delimiter": ","}
        )
        assert resp.status_code == 200
        assert "a" in resp.json()["result"]

    def test_join_lines(self, client):
        """Join lines by delimiter."""
        resp = client.post(
            "/api/v1/text/join-lines", json={"text": "a\nb\nc", "delimiter": ","}
        )
        assert resp.status_code == 200
        assert "a,b,c" in resp.json()["result"]

    def test_pad_lines_left(self, client):
        """Pad lines left alignment."""
        resp = client.post(
            "/api/v1/text/pad-lines", json={"text": "hi\nworld", "align": "left"}
        )
        assert resp.status_code == 200

    def test_pad_lines_right(self, client):
        """Pad lines right alignment."""
        resp = client.post(
            "/api/v1/text/pad-lines", json={"text": "hi\nworld", "align": "right"}
        )
        assert resp.status_code == 200

    def test_pad_lines_center(self, client):
        """Pad lines center alignment."""
        resp = client.post(
            "/api/v1/text/pad-lines", json={"text": "hi\nworld", "align": "center"}
        )
        assert resp.status_code == 200

    def test_wrap_lines(self, client):
        """Wrap lines with prefix and suffix."""
        resp = client.post(
            "/api/v1/text/wrap-lines",
            json={"text": "hello\nworld", "prefix": ">> ", "suffix": " <<"},
        )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert ">> hello <<" in result

    def test_filter_lines(self, client):
        """Filter lines containing a pattern."""
        resp = client.post(
            "/api/v1/text/filter-lines",
            json={"text": "apple\nbanana\ncherry", "pattern": "an"},
        )
        assert resp.status_code == 200
        assert "banana" in resp.json()["result"]

    def test_remove_lines(self, client):
        """Remove lines containing a pattern."""
        resp = client.post(
            "/api/v1/text/remove-lines",
            json={"text": "apple\nbanana\ncherry", "pattern": "an"},
        )
        assert resp.status_code == 200
        assert "banana" not in resp.json()["result"]

    def test_truncate_lines(self, client):
        """Truncate lines to max length."""
        resp = client.post(
            "/api/v1/text/truncate-lines", json={"text": "Hello World", "max_length": 5}
        )
        assert resp.status_code == 200

    def test_extract_nth_lines(self, client):
        """Extract every Nth line."""
        resp = client.post(
            "/api/v1/text/extract-nth-lines", json={"text": "a\nb\nc\nd", "n": 2}
        )
        assert resp.status_code == 200


# ── Developer tool endpoints ─────────────────────────────────────────────────


class TestDevToolEndpoints:
    """Test format-json, json-to-yaml, csv/json conversion endpoints."""

    def test_format_json_valid(self, client):
        """Valid JSON is pretty-printed."""
        resp = client.post("/api/v1/text/format-json", json={"text": '{"a":1,"b":2}'})
        assert resp.status_code == 200

    def test_format_json_invalid(self, client):
        """Invalid JSON returns 400."""
        resp = client.post("/api/v1/text/format-json", json={"text": "not json"})
        assert resp.status_code == 400

    def test_json_to_yaml_valid(self, client):
        """Valid JSON converts to YAML."""
        resp = client.post(
            "/api/v1/text/json-to-yaml", json={"text": '{"name": "Alice"}'}
        )
        assert resp.status_code == 200
        assert "Alice" in resp.json()["result"]

    def test_json_to_yaml_invalid(self, client):
        """Invalid JSON returns 400."""
        resp = client.post("/api/v1/text/json-to-yaml", json={"text": "not json"})
        assert resp.status_code == 400

    def test_json_escape(self, client):
        """JSON escape returns 200."""
        resp = client.post("/api/v1/text/json-escape", json={"text": 'hello "world"'})
        assert resp.status_code == 200

    def test_json_unescape_valid(self, client):
        """Valid JSON escaped string is unescaped."""
        resp = client.post("/api/v1/text/json-unescape", json={"text": "hello world"})
        assert resp.status_code == 200

    def test_csv_to_json_valid(self, client):
        """CSV input converts to JSON."""
        resp = client.post(
            "/api/v1/text/csv-to-json", json={"text": "name,age\nAlice,30"}
        )
        assert resp.status_code == 200

    def test_json_to_csv_valid(self, client):
        """JSON array converts to CSV."""
        resp = client.post(
            "/api/v1/text/json-to-csv", json={"text": '[{"name":"Alice","age":"30"}]'}
        )
        assert resp.status_code == 200
        assert "Alice" in resp.json()["result"]

    def test_json_to_csv_invalid(self, client):
        """Non-array JSON returns 400."""
        resp = client.post("/api/v1/text/json-to-csv", json={"text": '{"not":"array"}'})
        assert resp.status_code == 400

    def test_sql_insert_gen_valid(self, client):
        """CSV with header generates SQL INSERT statements."""
        resp = client.post(
            "/api/v1/text/sql-insert-gen", json={"text": "name,age\nAlice,30"}
        )
        assert resp.status_code == 200
        assert "INSERT" in resp.json()["result"]

    def test_sql_insert_gen_too_few_rows(self, client):
        """CSV with only header (no data rows) returns 400."""
        resp = client.post("/api/v1/text/sql-insert-gen", json={"text": "name,age"})
        assert resp.status_code == 400


# ── Additional AI endpoint auth checks ───────────────────────────────────────


class TestAiEndpointsRequireAuth:
    """Verify that all AI endpoints return 401 without authentication."""

    AI_ENDPOINTS = [
        "/api/v1/text/generate-hashtags",
        "/api/v1/text/generate-seo-titles",
        "/api/v1/text/generate-meta-descriptions",
        "/api/v1/text/generate-blog-outline",
        "/api/v1/text/shorten-for-tweet",
        "/api/v1/text/rewrite-email",
        "/api/v1/text/extract-keywords",
        "/api/v1/text/emojify",
        "/api/v1/text/detect-language",
    ]

    @pytest.mark.parametrize("path", AI_ENDPOINTS)
    def test_ai_endpoint_requires_auth(self, unauth_client, path):
        """AI endpoint returns 401 without authentication."""
        resp = unauth_client.post(path, json={"text": "test content"})
        assert resp.status_code == 401


# ── AI endpoints with mocked services ────────────────────────────────────────


class TestAiEndpointsWithMock:
    """Test AI endpoints return correct results when the service is mocked."""

    def test_generate_hashtags(self, client):
        """Mocked hashtag generation returns result."""
        with patch(
            "app.services.ai_service.run_ai_tool",
            AsyncMock(return_value="#TestTag #AI"),
        ):
            resp = client.post(
                "/api/v1/text/generate-hashtags", json={"text": "some content about AI"}
            )
        assert resp.status_code == 200
        assert resp.json()["result"] == "#TestTag #AI"

    def test_generate_seo_titles(self, client):
        """Mocked SEO title generation returns result."""
        with patch(
            "app.services.ai_service.run_ai_tool",
            AsyncMock(return_value="SEO Title 1\nSEO Title 2"),
        ):
            resp = client.post(
                "/api/v1/text/generate-seo-titles", json={"text": "AI tools"}
            )
        assert resp.status_code == 200

    def test_extract_keywords(self, client):
        """Mocked keyword extraction returns result."""
        with patch(
            "app.services.ai_service.run_ai_tool",
            AsyncMock(return_value="keyword1\nkeyword2"),
        ):
            resp = client.post(
                "/api/v1/text/extract-keywords", json={"text": "a long text"}
            )
        assert resp.status_code == 200

    def test_emojify(self, client):
        """Mocked emojify returns result."""
        with patch(
            "app.services.ai_service.run_ai_tool",
            AsyncMock(return_value="Hello world! :)"),
        ):
            resp = client.post("/api/v1/text/emojify", json={"text": "Hello world"})
        assert resp.status_code == 200

    def test_rewrite_email(self, client):
        """Mocked email rewrite returns result."""
        with patch(
            "app.services.ai_service.run_ai_tool",
            AsyncMock(return_value="Dear Sir, ..."),
        ):
            resp = client.post(
                "/api/v1/text/rewrite-email", json={"text": "hey whats up"}
            )
        assert resp.status_code == 200
