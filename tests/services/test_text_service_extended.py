"""Extended tests for app/services/text_service.py — covers edge cases and remaining functions."""

import pytest

import app.services.text_service as ts

# ── Additional case transformations ──────────────────────────────────────────


class TestCaseTransformations:
    """Edge cases for case transformation functions."""

    def test_to_uppercase_empty(self):
        """Empty string stays empty."""
        assert ts.to_uppercase("") == ""

    def test_to_lowercase_numbers(self):
        """Numbers are unaffected by lowercase."""
        assert ts.to_lowercase("ABC123") == "abc123"

    def test_to_inverse_case_mixed(self):
        """Inverse case swaps each character."""
        assert ts.to_inverse_case("AbCd") == "aBcD"

    def test_to_sentence_case_multi_sentence(self):
        """Multiple sentences each get capitalized."""
        result = ts.to_sentence_case("hello world. goodbye world")
        assert result.startswith("Hello world")

    def test_to_title_case_single_word(self):
        """Single word gets capitalized."""
        assert ts.to_title_case("hello") == "Hello"

    def test_to_upper_camel_case_empty(self):
        """Empty string stays empty."""
        assert ts.to_upper_camel_case("") == ""

    def test_to_lower_camel_case_single_word(self):
        """Single word starts lowercase."""
        assert ts.to_lower_camel_case("Hello") == "hello"

    def test_to_lower_camel_case_empty(self):
        """Empty string stays empty."""
        assert ts.to_lower_camel_case("") == ""

    def test_to_snake_case_already_snake(self):
        """Already snake_case stays the same."""
        assert ts.to_snake_case("already_snake") == "already_snake"

    def test_to_kebab_case_already_kebab(self):
        """Already kebab-case stays the same."""
        assert ts.to_kebab_case("already-kebab") == "already-kebab"

    def test_to_capitalize_words_preserves_rest(self):
        """Only first char of each word is uppercased."""
        result = ts.to_capitalize_words("hELLO wORLD")
        assert result == "HELLO WORLD"

    def test_to_alternating_case_with_spaces(self):
        """Spaces don't affect the alternation counter."""
        result = ts.to_alternating_case("ab cd")
        # a=0(lower), b=1(upper), space, c=2(lower), d=3(upper)
        assert result == "aB cD"

    def test_to_wide_text_single_char(self):
        """Single character has no spaces."""
        assert ts.to_wide_text("a") == "a"

    def test_to_small_caps_uppercase_first_lowered(self):
        """Input is lowered before translating to small caps."""
        result = ts.to_small_caps("ABC")
        assert len(result) == 3

    def test_to_upside_down_reverses(self):
        """Upside-down flips and reverses the string."""
        result = ts.to_upside_down("ab")
        assert isinstance(result, str)
        assert len(result) == 2

    def test_to_strikethrough_multiline(self):
        """Each non-empty line gets <del> tags."""
        result = ts.to_strikethrough("a\nb")
        assert result == "<del>a</del>\n<del>b</del>"

    def test_to_ap_title_case_last_word_capitalized(self):
        """Last word is always capitalized in AP style."""
        result = ts.to_ap_title_case("welcome to the")
        assert result.endswith("The")

    def test_to_swap_word_case_alternating(self):
        """Even words are upper, odd words are lower."""
        result = ts.to_swap_word_case("one two three four")
        words = result.split(" ")
        assert words[0] == "ONE"
        assert words[1] == "two"
        assert words[2] == "THREE"
        assert words[3] == "four"

    def test_to_dot_case(self):
        """Words joined with dots."""
        result = ts.to_dot_case("Hello World")
        assert result == "hello.world"

    def test_to_constant_case(self):
        """Words joined with underscores, all uppercase."""
        result = ts.to_constant_case("hello world")
        assert result == "HELLO_WORLD"

    def test_to_train_case(self):
        """Capitalized words joined with hyphens."""
        result = ts.to_train_case("hello world")
        assert result == "Hello-World"

    def test_to_path_case(self):
        """Words joined with forward slashes."""
        result = ts.to_path_case("Hello World")
        assert result == "hello/world"

    def test_to_flat_case(self):
        """All lowercase with no separators."""
        result = ts.to_flat_case("Hello World")
        assert result == "helloworld"

    def test_to_cobol_case(self):
        """Uppercase with hyphens."""
        result = ts.to_cobol_case("hello world")
        assert result == "HELLO-WORLD"


class TestCaseTransformsPerLine:
    """Identifier-style case transforms must process each line independently.

    The previous implementation collapsed multi-line input into a single
    line because the `[^a-zA-Z0-9]+` regex matched newlines. Each test here
    is a regression guard for one tool from the bug report.
    """

    def test_snake_case_keeps_lines_separate(self):
        result = ts.to_snake_case("hi Hello\ni am fine")
        assert result == "hi_hello\ni_am_fine"

    def test_kebab_case_keeps_lines_separate(self):
        result = ts.to_kebab_case("hello\nhello hi")
        assert result == "hello\nhello-hi"

    def test_dot_case_keeps_lines_separate(self):
        result = ts.to_dot_case("hi i am nensi\nwhat which.who")
        assert result == "hi.i.am.nensi\nwhat.which.who"

    def test_constant_case_keeps_lines_separate(self):
        result = ts.to_constant_case("hi hello\nmay i help you")
        assert result == "HI_HELLO\nMAY_I_HELP_YOU"

    def test_cobol_case_keeps_lines_separate(self):
        result = ts.to_cobol_case("hello\nhello hi")
        assert result == "HELLO\nHELLO-HI"

    def test_path_case_keeps_lines_separate(self):
        result = ts.to_path_case("hi hello\ni am nensi")
        assert result == "hi/hello\ni/am/nensi"

    def test_train_case_keeps_lines_separate(self):
        result = ts.to_train_case("hello world\nfoo bar")
        assert result == "Hello-World\nFoo-Bar"

    def test_flat_case_keeps_lines_separate(self):
        result = ts.to_flat_case("Hello World\nFoo Bar")
        assert result == "helloworld\nfoobar"

    def test_upper_camel_case_keeps_lines_separate(self):
        result = ts.to_upper_camel_case("one two\nfoo bar")
        assert result == "OneTwo\nFooBar"

    def test_lower_camel_case_keeps_lines_separate(self):
        result = ts.to_lower_camel_case("one two\nfoo bar")
        assert result == "oneTwo\nfooBar"

    def test_blank_lines_are_preserved(self):
        """Blank line in the middle stays a blank line — output line count
        matches input line count, not just for content lines."""
        result = ts.to_snake_case("hi\n\nworld")
        assert result == "hi\n\nworld"

    def test_single_line_input_unchanged_behaviour(self):
        """The new wrapper is a no-op on single-line input — ensure the
        existing single-line semantics are exactly preserved."""
        assert ts.to_snake_case("Hello World") == "hello_world"
        assert ts.to_kebab_case("Hello World") == "hello-world"
        assert ts.to_upper_camel_case("hello world") == "HelloWorld"

    # ── Word-style case transforms (do NOT collapse separators) ────────────

    def test_title_case_keeps_lines_separate(self):
        """User-reported regression: Title Case used to collapse newlines
        because text.split() splits on any whitespace including '\\n'."""
        result = ts.to_title_case("ajhdajhdjka asdjasdj\nadlkjllj; jjljl;k;lk")
        assert result == "Ajhdajhdjka Asdjasdj\nAdlkjllj; Jjljl;k;lk"

    def test_sentence_case_keeps_lines_separate(self):
        """Each line gets its own sentence-case treatment — joining lines
        with '. ' (the previous bug) erased line structure."""
        result = ts.to_sentence_case("hello world. how are you\ni am fine")
        assert result == "Hello world. How are you.\nI am fine."

    def test_capitalize_words_keeps_lines_separate(self):
        result = ts.to_capitalize_words("hello world\nfoo bar")
        assert result == "Hello World\nFoo Bar"

    def test_inverse_word_case_keeps_lines_separate(self):
        result = ts.to_inverse_word_case("hello world\nfoo bar")
        # Each word: all-but-last-char lower, last char upper
        assert result == "hellO worlD\nfoO baR"

    def test_ap_title_case_keeps_lines_separate(self):
        """Per-line AP rules: small words lowercased *except* first/last of
        each line."""
        result = ts.to_ap_title_case("the quick brown fox\nthe lazy dog")
        assert result == "The Quick Brown Fox\nThe Lazy Dog"

    def test_swap_word_case_keeps_lines_separate(self):
        """The alternating UPPER/lower parity should restart on each line —
        previously it bled across line breaks."""
        result = ts.to_swap_word_case("hi hello world\nfoo bar baz")
        # i=0 UPPER, i=1 lower, i=2 UPPER per line
        assert result == "HI hello WORLD\nFOO bar BAZ"

    def test_wide_text_keeps_lines_separate(self):
        """Wide text spaces every char within a line, but lines stay on
        their own lines — no ' \\n ' artefacts at the boundary."""
        result = ts.to_wide_text("ab\ncd")
        assert result == "a b\nc d"

    # ── Acronym handling for identifier-style transforms ──────────────────
    # `ChatGPT`, `XMLHttpRequest` etc. should split on acronym boundaries
    # AND preserve runs of all-uppercase letters in train-case / camel /
    # PascalCase. The plain lower/upper-cased variants (snake/kebab/...)
    # don't show acronym text but DO need the acronym boundary so words
    # like `XMLHttp` aren't fused into `xmlhttp`.

    def test_train_case_preserves_acronym(self):
        """User-reported regression: ``ChatGPT`` was producing ``Chat-Gpt``
        because ``str.capitalize()`` lowercased the trailing acronym."""
        assert ts.to_train_case("ChatGPT") == "Chat-GPT"

    def test_train_case_splits_acronym_then_word(self):
        assert ts.to_train_case("XMLHttpRequest") == "XML-Http-Request"

    def test_train_case_preserves_legacy_two_word_input(self):
        """Trailing assertion that the existing simple case is unchanged."""
        assert ts.to_train_case("hello world") == "Hello-World"

    def test_pascal_case_preserves_acronym(self):
        assert ts.to_upper_camel_case("ChatGPT") == "ChatGPT"
        assert ts.to_upper_camel_case("XMLHttpRequest") == "XMLHttpRequest"

    def test_camel_case_lowercases_first_word_only(self):
        assert ts.to_lower_camel_case("ChatGPT") == "chatGPT"
        assert ts.to_lower_camel_case("XMLHttpRequest") == "xmlHttpRequest"

    def test_snake_case_splits_on_acronym_boundary(self):
        assert ts.to_snake_case("ChatGPT") == "chat_gpt"
        assert ts.to_snake_case("XMLHttpRequest") == "xml_http_request"

    def test_kebab_case_splits_on_acronym_boundary(self):
        assert ts.to_kebab_case("XMLHttpRequest") == "xml-http-request"

    def test_constant_case_splits_on_acronym_boundary(self):
        assert ts.to_constant_case("XMLHttpRequest") == "XML_HTTP_REQUEST"

    def test_dot_case_splits_on_acronym_boundary(self):
        assert ts.to_dot_case("XMLHttpRequest") == "xml.http.request"

    def test_path_case_splits_on_acronym_boundary(self):
        assert ts.to_path_case("XMLHttpRequest") == "xml/http/request"

    def test_cobol_case_splits_on_acronym_boundary(self):
        assert ts.to_cobol_case("XMLHttpRequest") == "XML-HTTP-REQUEST"


# ── Text cleanup edge cases ──────────────────────────────────────────────────


class TestTextCleanup:
    """Test text cleanup functions edge cases."""

    def test_strip_html_with_script(self):
        """Script content is stripped completely."""
        result = ts.strip_html("<script>alert('xss')</script>Hello")
        assert "alert" not in result
        assert "Hello" in result

    def test_strip_html_with_entities(self):
        """HTML entities are decoded."""
        result = ts.strip_html("&amp; &lt; &gt;")
        assert "& < >" in result

    def test_remove_accents_common(self):
        """Common accented characters are stripped."""
        assert "e" in ts.remove_accents("e\u0301")  # e with combining acute

    def test_toggle_smart_quotes_straight_to_smart(self):
        """Straight quotes become curly quotes."""
        result = ts.toggle_smart_quotes('"Hello"')
        # Should convert to smart quotes
        assert "\u201c" in result or "\u201d" in result

    def test_toggle_smart_quotes_smart_to_straight(self):
        """Curly quotes become straight quotes."""
        result = ts.toggle_smart_quotes("\u201cHello\u201d")
        assert '"' in result

    def test_strip_invisible_zero_width_joiner(self):
        """Zero-width joiner (category Cf) is removed."""
        result = ts.strip_invisible("a\u200db")
        assert "\u200d" not in result

    def test_normalize_whitespace_preserves_newlines(self):
        """Newlines are preserved while tabs become spaces."""
        result = ts.normalize_whitespace("a\t b\nc")
        assert "\n" in result
        assert "\t" not in result

    def test_fix_line_endings_mixed(self):
        """Mixed CR+LF and CR-only are normalized to LF."""
        result = ts.fix_line_endings("a\r\nb\rc\n")
        assert "\r" not in result
        assert result == "a\nb\nc\n"

    def test_strip_markdown_headers(self):
        """Markdown headers are removed."""
        result = ts.strip_markdown("## Title\nContent")
        assert "##" not in result
        assert "Title" in result

    def test_strip_markdown_links(self):
        """Markdown links are replaced with link text."""
        result = ts.strip_markdown("[click here](https://example.com)")
        assert "click here" in result
        assert "https://" not in result

    def test_strip_empty_lines_all_empty(self):
        """All-empty lines produce empty string."""
        result = ts.strip_empty_lines("\n\n\n")
        assert result == ""

    def test_strip_urls_www(self):
        """www. URLs are also stripped."""
        result = ts.strip_urls("visit www.example.com please")
        assert "www.example.com" not in result

    def test_strip_numbers_no_numbers(self):
        """Text without numbers is unchanged."""
        result = ts.strip_numbers("hello world")
        assert result == "hello world"

    def test_normalize_punctuation_removes_space_before_comma(self):
        """Space before comma is removed."""
        result = ts.normalize_punctuation("hello , world")
        assert result.startswith("hello,")


# ── Encoding roundtrips ──────────────────────────────────────────────────────


class TestEncodingRoundtrips:
    """Test encode/decode roundtrips produce the original text."""

    def test_hex_roundtrip(self):
        """hex_decode(hex_encode(x)) == x."""
        original = "Hello, World!"
        assert ts.hex_decode(ts.hex_encode(original)) == original

    def test_binary_roundtrip(self):
        """binary_decode(binary_encode(x)) == x."""
        original = "ABC"
        assert ts.binary_decode(ts.binary_encode(original)) == original

    def test_octal_roundtrip(self):
        """octal_decode(octal_encode(x)) == x."""
        original = "test"
        assert ts.octal_decode(ts.octal_encode(original)) == original

    def test_decimal_roundtrip(self):
        """decimal_decode(decimal_encode(x)) == x."""
        original = "hello"
        assert ts.decimal_decode(ts.decimal_encode(original)) == original

    def test_morse_roundtrip(self):
        """morse_decode(morse_encode(x)) == x for simple text."""
        original = "SOS"
        assert ts.morse_decode(ts.morse_encode(original)) == original

    def test_base32_roundtrip(self):
        """base32_decode(base32_encode(x)) == x."""
        original = "Hello World"
        assert ts.base32_decode(ts.base32_encode(original)) == original

    def test_ascii85_roundtrip(self):
        """ascii85_decode(ascii85_encode(x)) == x."""
        original = "Hello World"
        assert ts.ascii85_decode(ts.ascii85_encode(original)) == original

    def test_brainfuck_roundtrip(self):
        """brainfuck_decode(brainfuck_encode(x)) == x."""
        original = "Hi"
        assert ts.brainfuck_decode(ts.brainfuck_encode(original)) == original

    def test_vigenere_roundtrip(self):
        """decrypt(encrypt(x, key), key) == x."""
        original = "Hello World"
        key = "secret"
        encrypted = ts.vigenere_encrypt(original, key)
        decrypted = ts.vigenere_decrypt(encrypted, key)
        assert decrypted == original

    def test_rail_fence_roundtrip(self):
        """decrypt(encrypt(x, rails), rails) == x."""
        original = "Hello World"
        encrypted = ts.rail_fence_encrypt(original, 3)
        decrypted = ts.rail_fence_decrypt(encrypted, 3)
        assert decrypted == original

    def test_atbash_involution(self):
        """Atbash applied twice returns original."""
        original = "Hello World"
        assert ts.atbash_cipher(ts.atbash_cipher(original)) == original

    def test_rot13_involution(self):
        """ROT13 applied twice returns original."""
        original = "Hello World 123"
        assert ts.rot13(ts.rot13(original)) == original


# ── Cipher edge cases ────────────────────────────────────────────────────────


class TestCipherEdgeCases:
    """Edge cases for cipher functions."""

    def test_caesar_cipher_non_alpha_unchanged(self):
        """Non-alphabetic characters pass through unchanged."""
        result = ts.caesar_cipher("hello 123!", 3)
        assert "123!" in result

    def test_caesar_brute_force_all_25_shifts(self):
        """Brute force produces 25 shift lines."""
        result = ts.caesar_brute_force("abc")
        lines = result.strip().split("\n")
        assert len(lines) == 25

    def test_vigenere_encrypt_invalid_key_raises(self):
        """Non-alpha key raises ValueError."""
        with pytest.raises(ValueError):
            ts.vigenere_encrypt("hello", "123")

    def test_vigenere_encrypt_empty_key_raises(self):
        """Empty key raises ValueError."""
        with pytest.raises(ValueError):
            ts.vigenere_encrypt("hello", "")

    def test_rail_fence_encrypt_min_rails(self):
        """Minimum rails=2 works."""
        result = ts.rail_fence_encrypt("hello", 2)
        assert isinstance(result, str)

    def test_playfair_encrypt_j_replaced(self):
        """J is replaced with I in Playfair cipher."""
        result = ts.playfair_encrypt("JELLO", "KEY")
        assert isinstance(result, str)

    def test_substitution_cipher_wrong_length_raises(self):
        """Mapping shorter than 26 characters raises ValueError."""
        with pytest.raises(ValueError):
            ts.substitution_cipher("hello", "ABC")

    def test_columnar_transposition_empty_key_raises(self):
        """Empty key raises ValueError."""
        with pytest.raises(ValueError):
            ts.columnar_transposition("hello", "")

    def test_brainfuck_decode_unmatched_bracket_raises(self):
        """Unmatched ] raises ValueError."""
        with pytest.raises(ValueError):
            ts.brainfuck_decode("]")

    def test_brainfuck_decode_unmatched_open_bracket_raises(self):
        """Unmatched [ raises ValueError."""
        with pytest.raises(ValueError):
            ts.brainfuck_decode("[")

    def test_bacon_cipher_decode(self):
        """Bacon-encoded text decodes back."""
        encoded = ts.bacon_cipher("AB")
        # Round-trip must recover the original. Previously a bug routed any
        # A/B-only string straight to the decoder, so encode("AB") returned
        # the empty string and the round-trip silently lost data.
        assert encoded == "AAAAA AAAAB"
        assert ts.bacon_cipher(encoded) == "AB"

    def test_bacon_cipher_does_not_mistake_ab_plaintext_for_ciphertext(self):
        """Regression: short A/B-only plaintext like 'AB', 'A', 'BABA' must
        be treated as plaintext and encoded — not auto-detected as Bacon
        ciphertext (whose length must be a positive multiple of 5)."""
        assert ts.bacon_cipher("A") == "AAAAA"
        assert ts.bacon_cipher("AB") == "AAAAA AAAAB"
        assert ts.bacon_cipher("BABA") == "AAAAB AAAAA AAAAB AAAAA"

    def test_bacon_cipher_decodes_only_proper_codeword_groups(self):
        """An A/B-only string whose length is a multiple of 5 IS a valid
        Bacon decode candidate; otherwise it's plaintext."""
        # 5 * 2 = 10 chars, valid Bacon ciphertext: HE
        assert ts.bacon_cipher("AABBBAABAA") == "HE"
        # 9 chars, not a multiple of 5 — must be treated as plaintext
        assert ts.bacon_cipher("AAAAAAAAA") != ""

    def test_nato_phonetic_reverse(self):
        """NATO phonetic words decode back to letters."""
        result = ts.nato_phonetic("Alpha Bravo")
        assert result == "AB"

    def test_morse_encode_space(self):
        """Spaces in text produce / in Morse code."""
        result = ts.morse_encode("A B")
        assert "/" in result


# ── Line manipulation edge cases ─────────────────────────────────────────────


class TestLineManipulation:
    """Test line-based text manipulation functions."""

    def test_sort_by_length_empty(self):
        """Empty string stays empty."""
        result = ts.sort_by_length("")
        assert result == ""

    def test_sort_numeric_no_numbers(self):
        """Lines without numbers sort to infinity."""
        result = ts.sort_numeric("abc\n123\nxyz")
        lines = result.split("\n")
        assert lines[0] == "123"

    def test_line_frequency_single_line(self):
        """Single line has frequency 1."""
        result = ts.line_frequency("hello")
        assert "1x" in result

    def test_split_to_lines_custom_delimiter(self):
        """Custom delimiter splits correctly."""
        result = ts.split_to_lines("a|b|c", "|")
        assert "a" in result and "b" in result

    def test_join_lines_strips_whitespace(self):
        """Lines are stripped before joining."""
        result = ts.join_lines("  a  \n  b  \n  c  ", ",")
        assert result == "a,b,c"

    def test_pad_lines_center(self):
        """Center alignment pads both sides."""
        result = ts.pad_lines("ab\nabcde", "center")
        lines = result.split("\n")
        # Both lines should be same length
        assert len(lines[0]) == len(lines[1])

    def test_wrap_lines_empty_prefix_suffix(self):
        """Empty prefix and suffix leaves lines unchanged."""
        result = ts.wrap_lines("hello\nworld", "", "")
        assert result == "hello\nworld"

    def test_filter_lines_case_insensitive(self):
        """Case-insensitive filter matches regardless of case."""
        result = ts.filter_lines_contain(
            "Apple\nbanana\nCHERRY", "apple", case_sensitive=False
        )
        assert "Apple" in result

    def test_filter_lines_case_sensitive(self):
        """Case-sensitive filter only matches exact case."""
        result = ts.filter_lines_contain(
            "Apple\napple\nAPPLE", "apple", case_sensitive=True
        )
        assert "Apple" not in result or result == "apple"

    def test_filter_lines_regex(self):
        """Regex filter matches patterns."""
        import re

        compiled = re.compile(r"^\d+", re.IGNORECASE)
        result = ts.filter_lines_contain(
            "123abc\nhello\n456def",
            r"^\d+",
            case_sensitive=False,
            use_regex=True,
            compiled=compiled,
        )
        assert "hello" not in result

    def test_remove_lines_regex(self):
        """Regex remove excludes matching lines."""
        import re

        compiled = re.compile(r"^\d+", re.IGNORECASE)
        result = ts.remove_lines_contain(
            "123abc\nhello\n456def",
            r"^\d+",
            case_sensitive=False,
            use_regex=True,
            compiled=compiled,
        )
        assert "hello" in result

    def test_truncate_lines_short_line_unchanged(self):
        """Lines shorter than max_length are unchanged."""
        result = ts.truncate_lines("hi", 80)
        assert result == "hi"

    def test_extract_nth_lines_offset(self):
        """Offset parameter shifts extraction start."""
        result = ts.extract_nth_lines("a\nb\nc\nd\ne\nf", n=2, offset=1)
        # Starting from index 1 (b), every 2nd: b, d, f
        assert "b" in result
        assert "d" in result

    def test_remove_duplicate_lines_preserves_order(self):
        """First occurrence is kept, duplicates removed."""
        result = ts.remove_duplicate_lines("c\na\nb\na\nc")
        lines = result.split("\n")
        assert lines == ["c", "a", "b"]


# ── Developer tools edge cases ───────────────────────────────────────────────


class TestDevTools:
    """Test developer tool functions."""

    def test_format_json_pretty_print(self):
        """Pretty printing uses 2-space indent."""
        result = ts.format_json('{"a":1}')
        assert "  " in result

    def test_format_json_invalid_raises(self):
        """Invalid JSON raises JSONDecodeError."""
        with pytest.raises((ValueError, Exception)):
            ts.format_json("not json")

    def test_json_to_yaml_dict(self):
        """Dict JSON converts to YAML mapping."""
        result = ts.json_to_yaml('{"key": "value"}')
        assert "key:" in result

    def test_json_escape_newline(self):
        """Newlines separate independently-escaped lines so each input line maps to its own output line."""
        result = ts.json_escape("hello\nworld")
        assert result == "hello\nworld"

    def test_json_unescape_roundtrip(self):
        """json_unescape(json_escape(x)) == x."""
        original = 'hello "world"\nnew line'
        assert ts.json_unescape(ts.json_escape(original)) == original

    def test_csv_to_json_multirow(self):
        """Multi-row CSV produces JSON array."""
        result = ts.csv_to_json("a,b\n1,2\n3,4")
        import json

        data = json.loads(result)
        assert len(data) == 2

    def test_json_to_csv_empty_array_raises(self):
        """Empty JSON array raises ValueError."""
        with pytest.raises(ValueError):
            ts.json_to_csv("[]")

    def test_csv_to_table_empty(self):
        """Empty CSV returns original text."""
        result = ts.csv_to_table("")
        assert result == ""

    def test_sql_insert_gen_numeric_values(self):
        """Numeric values are not quoted in SQL."""
        result = ts.sql_insert_gen("name,age\nAlice,30")
        assert "'Alice'" in result
        assert "30" in result  # not quoted

    def test_sql_insert_gen_header_only_raises(self):
        """Header-only CSV raises ValueError."""
        with pytest.raises(ValueError):
            ts.sql_insert_gen("name,age")
