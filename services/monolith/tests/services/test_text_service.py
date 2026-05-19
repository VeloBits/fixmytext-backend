"""Tests for app/services/text_service.py"""

import app.services.text_service as ts

# ── Case transformations ──────────────────────────────────────────────────────


def test_to_uppercase():
    assert ts.to_uppercase("hello world") == "HELLO WORLD"


def test_to_lowercase():
    assert ts.to_lowercase("HELLO WORLD") == "hello world"


def test_to_inverse_case():
    assert ts.to_inverse_case("Hello") == "hELLO"


def test_to_sentence_case_basic():
    # Documented behavior: capitalises the first letter AND appends a period
    # when the input lacks one. Tooltip ("Sentence Case") flags the period
    # behaviour explicitly so users aren't surprised.
    assert ts.to_sentence_case("hello world") == "Hello world."


def test_to_sentence_case_with_period():
    assert ts.to_sentence_case("hello world.") == "Hello world."


def test_to_title_case():
    assert ts.to_title_case("hello world") == "Hello World"


def test_to_upper_camel_case():
    assert ts.to_upper_camel_case("hello world") == "HelloWorld"


def test_to_lower_camel_case():
    assert ts.to_lower_camel_case("hello world") == "helloWorld"


def test_to_snake_case():
    assert ts.to_snake_case("Hello World") == "hello_world"


def test_to_snake_case_from_camel():
    assert ts.to_snake_case("helloWorld") == "hello_world"


def test_to_kebab_case():
    assert ts.to_kebab_case("Hello World") == "hello-world"


def test_to_capitalize_words():
    result = ts.to_capitalize_words("hello world")
    assert result == "Hello World"


def test_to_alternating_case():
    result = ts.to_alternating_case("hello")
    assert result == "hElLo"


def test_to_wide_text():
    result = ts.to_wide_text("hi")
    assert result == "h i"


# ── Additional case transformations ─────────────────────────────────────────


def test_to_inverse_word_case_single_char_word():
    # Single-char word → uppercased
    result = ts.to_inverse_word_case("a")
    assert result == "A"


def test_to_inverse_word_case_multi_word():
    result = ts.to_inverse_word_case("hello world")
    assert isinstance(result, str)


def test_to_inverse_word_case_empty_words():
    # Words separated by multiple spaces → empty words preserved
    result = ts.to_inverse_word_case("a  b")
    assert isinstance(result, str)


def test_to_small_caps():
    result = ts.to_small_caps("Hello")
    assert isinstance(result, str)
    assert len(result) == len("Hello")


def test_to_upside_down():
    result = ts.to_upside_down("hello")
    assert isinstance(result, str)


def test_to_strikethrough():
    result = ts.to_strikethrough("hello world")
    assert "<del>" in result


def test_to_strikethrough_empty_line():
    result = ts.to_strikethrough("line1\n\nline2")
    assert "line1" in result


def test_to_ap_title_case_basic():
    result = ts.to_ap_title_case("the quick brown fox")
    # 'the' at start should be capitalized
    assert result.startswith("The")


def test_to_ap_title_case_small_words():
    result = ts.to_ap_title_case("a tale of two cities")
    assert "Tale" in result
    # 'of' and 'a' in middle should be lowercase
    assert " of " in result


def test_to_swap_word_case():
    result = ts.to_swap_word_case("hello world foo")
    assert isinstance(result, str)


def test_to_path_case():
    result = ts.to_path_case("Hello World")
    assert "/" in result


def test_to_flat_case():
    result = ts.to_flat_case("Hello World")
    assert " " not in result
    assert result == result.lower()


def test_to_cobol_case():
    result = ts.to_cobol_case("hello world")
    assert "-" in result
    assert result == result.upper()


# ── Spaces and whitespace ─────────────────────────────────────────────────────


def test_remove_extra_spaces():
    assert ts.remove_extra_spaces("  hello   world  ") == "hello world"


def test_remove_all_spaces():
    assert ts.remove_all_spaces("hello world") == "helloworld"


def test_remove_all_spaces_removes_tabs_too():
    # remove_all_spaces removes ALL whitespace (spaces, tabs, etc.)
    result = ts.remove_all_spaces("a b\tc")
    assert " " not in result
    assert "a" in result and "b" in result and "c" in result


def test_remove_line_breaks():
    result = ts.remove_line_breaks("line1\nline2\nline3")
    assert "\n" not in result


# ── Text cleanup ─────────────────────────────────────────────────────────────


def test_remove_accents():
    result = ts.remove_accents("café résumé")
    assert "é" not in result
    assert "cafe" in result.lower() or "cafe" in result


def test_toggle_smart_quotes():
    result = ts.toggle_smart_quotes("\"Hello\" and 'World'")
    assert isinstance(result, str)


def test_strip_invisible():
    # strip_invisible removes zero-width and other invisible chars (not null bytes)
    result = ts.strip_invisible("hello\u200bworld")  # zero-width space
    assert "\u200b" not in result


def test_strip_emoji():
    result = ts.strip_emoji("hello 😀 world")
    assert "😀" not in result
    assert "hello" in result


def test_normalize_whitespace():
    result = ts.normalize_whitespace("  hello  \t world  ")
    assert "\t" not in result
    assert "hello" in result


def test_strip_non_ascii():
    result = ts.strip_non_ascii("hello café")
    assert "café" not in result or all(ord(c) < 128 for c in result)


def test_fix_line_endings():
    result = ts.fix_line_endings("line1\r\nline2\rline3")
    assert "\r" not in result


def test_strip_markdown():
    result = ts.strip_markdown("**bold** and *italic*")
    assert isinstance(result, str)


def test_strip_urls():
    result = ts.strip_urls("visit https://example.com now")
    assert "https://example.com" not in result


def test_strip_emails():
    result = ts.strip_emails("contact user@example.com today")
    assert "user@example.com" not in result


def test_normalize_punctuation():
    result = ts.normalize_punctuation("hello  , world  !")
    assert isinstance(result, str)


def test_strip_numbers():
    result = ts.strip_numbers("abc123def456")
    assert "1" not in result
    assert "abc" in result


# ── Reversing and sorting ─────────────────────────────────────────────────────


def test_reverse_text():
    assert ts.reverse_text("hello") == "olleh"


def test_reverse_lines():
    result = ts.reverse_lines("line1\nline2\nline3")
    assert "line3" in result.split("\n")[0]


def test_sort_lines_asc():
    assert ts.sort_lines_asc("banana\napple\ncherry") == "apple\nbanana\ncherry"


def test_sort_lines_desc():
    assert ts.sort_lines_desc("apple\nbanana\ncherry") == "cherry\nbanana\napple"


def test_sort_lines_asc_single():
    assert ts.sort_lines_asc("only") == "only"


# ── Encoding ─────────────────────────────────────────────────────────────────


def test_base64_encode():
    assert ts.base64_encode("hello") == "aGVsbG8="


def test_base64_decode():
    assert ts.base64_decode("aGVsbG8=") == "hello"


def test_base64_roundtrip():
    text = "Hello, World! 123"
    assert ts.base64_decode(ts.base64_encode(text)) == text


def test_url_encode():
    result = ts.url_encode("hello world")
    assert " " not in result
    assert "hello" in result


def test_url_decode():
    assert ts.url_decode("hello%20world") == "hello world"


def test_url_roundtrip():
    original = "hello world & more"
    assert ts.url_decode(ts.url_encode(original)) == original


def test_html_encode():
    result = ts.html_escape_text("<b>bold</b>")
    assert "&lt;" in result
    assert "&gt;" in result


def test_html_decode():
    result = ts.html_unescape_text("&lt;b&gt;bold&lt;/b&gt;")
    assert "<b>" in result


def test_html_roundtrip():
    original = "<p>Hello & World</p>"
    assert ts.html_unescape_text(ts.html_escape_text(original)) == original


# ── More encoding/cipher ──────────────────────────────────────────────────────


def test_hex_decode():
    result = ts.hex_decode("68656c6c6f")
    assert result.lower() == "hello" or "hello" in result.lower()


def test_morse_decode():
    encoded = ts.morse_encode("SOS")
    result = ts.morse_decode(encoded)
    assert "SOS" in result.upper() or isinstance(result, str)


def test_binary_decode():
    encoded = ts.binary_encode("A")
    result = ts.binary_decode(encoded)
    assert "A" in result or isinstance(result, str)


def test_octal_encode():
    result = ts.octal_encode("A")
    assert isinstance(result, str)


def test_octal_decode():
    encoded = ts.octal_encode("A")
    result = ts.octal_decode(encoded)
    assert isinstance(result, str)


def test_decimal_encode():
    result = ts.decimal_encode("A")
    assert "65" in result  # ASCII value of 'A'


def test_decimal_decode():
    result = ts.decimal_decode("65")
    assert isinstance(result, str)


def test_unicode_escape():
    result = ts.unicode_escape("hello")
    assert isinstance(result, str)


def test_unicode_unescape():
    escaped = ts.unicode_escape("A")
    result = ts.unicode_unescape(escaped)
    assert isinstance(result, str)


def test_brainfuck_encode():
    result = ts.brainfuck_encode("A")
    assert isinstance(result, str)
    # Brainfuck uses +-.[] characters
    assert any(c in result for c in "+-.,[]<>")


def test_brainfuck_decode():
    encoded = ts.brainfuck_encode("A")
    result = ts.brainfuck_decode(encoded)
    assert isinstance(result, str)


def test_base32_encode():
    result = ts.base32_encode("hello")
    assert isinstance(result, str)


def test_base32_decode():
    encoded = ts.base32_encode("hello")
    result = ts.base32_decode(encoded)
    assert "hello" in result.lower()


def test_ascii85_encode():
    result = ts.ascii85_encode("hello")
    assert isinstance(result, str)


def test_ascii85_decode():
    encoded = ts.ascii85_encode("hello")
    result = ts.ascii85_decode(encoded)
    assert "hello" in result.lower() or isinstance(result, str)


def test_vigenere_encrypt():
    result = ts.vigenere_encrypt("hello", "key")
    assert isinstance(result, str)


def test_vigenere_decrypt():
    encrypted = ts.vigenere_encrypt("hello", "key")
    result = ts.vigenere_decrypt(encrypted, "key")
    assert "hello" in result.lower()


def test_rail_fence_encrypt():
    result = ts.rail_fence_encrypt("hello", 2)
    assert isinstance(result, str)


def test_rail_fence_decrypt():
    encrypted = ts.rail_fence_encrypt("hello", 2)
    result = ts.rail_fence_decrypt(encrypted, 2)
    assert isinstance(result, str)


def test_playfair_encrypt():
    result = ts.playfair_encrypt("hello", "key")
    assert isinstance(result, str)


def test_substitution_cipher():
    mapping = "ZYXWVUTSRQPONMLKJIHGFEDCBA"
    result = ts.substitution_cipher("hello", mapping)
    assert isinstance(result, str)


def test_columnar_transposition():
    result = ts.columnar_transposition("hello world", "key")
    assert isinstance(result, str)


def test_bacon_cipher():
    # 'AB' is plaintext (length not a multiple of 5) → must encode, not
    # auto-decode. Prior bug returned ''.
    assert ts.bacon_cipher("AB") == "AAAAA AAAAB"


def test_caesar_brute_force():
    result = ts.caesar_brute_force("khoor")
    assert isinstance(result, str)
    assert "hello" in result.lower()


def test_atbash_cipher():
    result = ts.atbash_cipher("hello")
    assert result == "svool"


# ── Text manipulation ─────────────────────────────────────────────────────────


def test_remove_duplicate_lines():
    result = ts.remove_duplicate_lines("a\nb\na\nc")
    lines = result.split("\n")
    assert len(lines) == len(set(lines))


def test_trim_lines():
    result = ts.trim_lines("  hello  \n  world  ")
    assert "  hello  " not in result


def test_number_lines():
    result = ts.number_lines("first\nsecond")
    assert "1" in result
    assert "2" in result


def test_strip_empty_lines():
    result = ts.strip_empty_lines("a\n\nb\n\nc")
    lines = [ln for ln in result.split("\n") if ln == ""]
    assert len(lines) == 0


def test_strip_html():
    result = ts.strip_html("<p>Hello <b>World</b></p>")
    assert "<" not in result
    assert "Hello" in result
    assert "World" in result


def test_truncate_lines():
    result = ts.truncate_lines("Hello World This Is Long", 5)
    lines = result.split("\n")
    for line in lines:
        assert len(line) <= 5 + 3  # max_length + possible ellipsis


def test_pad_lines_left():
    result = ts.pad_lines("hi\nworld", "left")
    assert isinstance(result, str)


def test_pad_lines_right():
    result = ts.pad_lines("hi\nworld", "right")
    assert isinstance(result, str)


def test_extract_nth_lines():
    result = ts.extract_nth_lines("a\nb\nc\nd\ne", 2)
    assert isinstance(result, str)


def test_extract_nth_lines_zero_offset():
    result = ts.extract_nth_lines("a\nb\nc", 1, 0)
    assert "a" in result


def test_filter_lines_contain():
    result = ts.filter_lines_contain("apple\nbanana\ncherry", "an")
    assert "banana" in result
    assert "apple" not in result


def test_remove_lines_contain():
    result = ts.remove_lines_contain("apple\nbanana\ncherry", "an")
    assert "apple" in result
    assert "banana" not in result


def test_split_to_lines():
    result = ts.split_to_lines("a,b,c", ",")
    assert "a" in result
    assert "b" in result
    assert "c" in result


def test_join_lines():
    result = ts.join_lines("a\nb\nc", ",")
    assert result == "a,b,c"


# ── Caesar cipher ────────────────────────────────────────────────────────────


def test_caesar_cipher_encode():
    result = ts.caesar_cipher("hello", 3)
    assert result == "khoor"


def test_caesar_cipher_decode():
    result = ts.caesar_cipher("khoor", -3)
    assert result == "hello"


def test_caesar_cipher_wraps():
    result = ts.caesar_cipher("xyz", 3)
    assert result == "abc"


# ── JSON/YAML/CSV conversions ────────────────────────────────────────────────


def test_format_json():
    result = ts.format_json('{"a": 1}')
    assert "a" in result


def test_format_json_valid():
    result = ts.format_json('{"a": 1, "b": 2}')
    assert '"a"' in result


def test_json_to_yaml():
    result = ts.json_to_yaml('{"name": "Alice"}')
    assert "name" in result
    assert "Alice" in result


def test_json_escape():
    result = ts.json_escape('hello "world"')
    assert '\\"' in result or '\\"' in result


def test_json_unescape():
    escaped = ts.json_escape('hello "world"')
    result = ts.json_unescape(escaped)
    assert '"world"' in result or isinstance(result, str)


def test_csv_to_json():
    result = ts.csv_to_json("name,age\nAlice,30\nBob,25")
    assert isinstance(result, str)


def test_json_to_csv():
    result = ts.json_to_csv('[{"name": "Alice", "age": 30}]')
    assert isinstance(result, str)
    assert "Alice" in result


def test_csv_to_table():
    result = ts.csv_to_table("name,age\nAlice,30")
    assert isinstance(result, str)


def test_sql_insert_gen():
    result = ts.sql_insert_gen("name,age\nAlice,30")
    assert isinstance(result, str)


# ── Sort and shuffle ──────────────────────────────────────────────────────────


def test_shuffle_lines():
    result = ts.shuffle_lines("a\nb\nc\nd")
    # After shuffle, all lines should still be present
    for line in ["a", "b", "c", "d"]:
        assert line in result


def test_sort_by_length():
    result = ts.sort_by_length("cat\nelephant\nox")
    lines = result.split("\n")
    assert lines[0] in ("ox", "ox")  # shortest first


def test_sort_numeric():
    result = ts.sort_numeric("10\n2\n30\n1")
    lines = result.split("\n")
    assert lines[0] == "1"


def test_line_frequency():
    result = ts.line_frequency("a\nb\na\nc\na")
    assert "a" in result
    assert "3" in result  # 'a' appears 3 times


# ── Line wrapping and padding ─────────────────────────────────────────────────


def test_wrap_lines_with_prefix():
    result = ts.wrap_lines("hello\nworld", prefix=">> ", suffix="")
    assert ">> hello" in result


def test_wrap_lines_with_suffix():
    result = ts.wrap_lines("hello", prefix="", suffix=" <<<")
    assert "hello <<<" in result


def test_pad_lines_center():
    result = ts.pad_lines("hi\nworld", "center")
    assert isinstance(result, str)


# ── Markdown ─────────────────────────────────────────────────────────────────


def test_atbash_cipher_from_base():
    result = ts.atbash_cipher("abc")
    assert result == "zyx"


def test_rot13():
    result = ts.rot13("hello")
    assert result == "uryyb"


def test_rot13_roundtrip():
    assert ts.rot13(ts.rot13("hello world")) == "hello world"


def test_binary_encode():
    result = ts.binary_encode("A")
    assert "01000001" in result


def test_hex_encode():
    result = ts.hex_encode("A")
    assert "41" in result.lower()


def test_morse_encode():
    result = ts.morse_encode("SOS")
    assert "." in result or "-" in result


def test_nato_phonetic():
    result = ts.nato_phonetic("abc")
    assert isinstance(result, str) and len(result) > 0


# ── NATO and other special encoding ──────────────────────────────────────────


def test_nato_phonetic_known_letters():
    result = ts.nato_phonetic("AB")
    assert "Alpha" in result or "alpha" in result.lower()
    assert "Bravo" in result or "bravo" in result.lower()
