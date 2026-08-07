"""Unit tests for app.services.text_service.

The transforms are pure, synchronous functions - they are tested directly
(no HTTP layer) for speed and precision. Endpoint dispatch is covered in
test_text_endpoints.py / test_text_endpoints_extra.py.
"""

import json
import re

import pytest
import regex
import yaml

import app.services.text_service as ts

# ── Case transformations ──────────────────────────────────────────────────


def test_to_uppercase():
    assert ts.to_uppercase("hello") == "HELLO"


def test_to_lowercase():
    assert ts.to_lowercase("HeLLo") == "hello"


def test_to_inverse_case():
    assert ts.to_inverse_case("Hello World") == "hELLO wORLD"


def test_to_sentence_case_multiple_sentences():
    assert ts.to_sentence_case("hello world. this is fine!") == (
        "Hello world. This is fine!"
    )


def test_to_sentence_case_preserves_blank_lines():
    assert ts.to_sentence_case("one. two\n\nthree") == "One. Two.\n\nThree."


def test_to_sentence_case_adds_trailing_period():
    assert ts.to_sentence_case("what? yes") == "What. Yes."


def test_to_title_case():
    assert ts.to_title_case("hello world") == "Hello World"


def test_to_upper_camel_case_preserves_acronyms():
    assert ts.to_upper_camel_case("chat GPT") == "ChatGPT"
    assert ts.to_upper_camel_case("XMLHttpRequest") == "XMLHttpRequest"


def test_to_lower_camel_case():
    assert ts.to_lower_camel_case("Hello World") == "helloWorld"
    assert ts.to_lower_camel_case("XML http request") == "xmlHttpRequest"


def test_to_lower_camel_case_no_words():
    assert ts.to_lower_camel_case("!!!") == ""


def test_to_snake_case_splits_acronym_boundaries():
    assert ts.to_snake_case("XMLHttpRequest") == "xml_http_request"
    assert ts.to_snake_case("Hello World-Test") == "hello_world_test"


def test_to_kebab_case():
    assert ts.to_kebab_case("Hello World") == "hello-world"


def test_case_transforms_are_per_line():
    assert ts.to_snake_case("Hello World\nFoo Bar") == "hello_world\nfoo_bar"


def test_to_capitalize_words_preserves_spacing():
    assert ts.to_capitalize_words("hello  world") == "Hello  World"


def test_to_alternating_case_counts_letters_only():
    assert ts.to_alternating_case("abcd ef") == "aBcD eF"


def test_to_inverse_word_case():
    assert ts.to_inverse_word_case("hi a") == "hI A"


def test_to_wide_text():
    assert ts.to_wide_text("ab\ncd") == "a b\nc d"


def test_to_small_caps():
    assert ts.to_small_caps("Hello") == "ʜᴇʟʟᴏ"


def test_to_upside_down():
    assert ts.to_upside_down("abc") == "ɔqɐ"


def test_to_strikethrough_skips_blank_lines():
    assert ts.to_strikethrough("hi\n\nyo") == "<del>hi</del>\n\n<del>yo</del>"


def test_to_ap_title_case_keeps_small_words_lowercase():
    assert ts.to_ap_title_case("the war of the worlds") == "The War of the Worlds"


def test_to_swap_word_case():
    assert ts.to_swap_word_case("one two three") == "ONE two THREE"


def test_to_dot_case():
    assert ts.to_dot_case("Hello World") == "hello.world"


def test_to_constant_case():
    assert ts.to_constant_case("hello world") == "HELLO_WORLD"


def test_to_train_case_preserves_acronyms():
    assert ts.to_train_case("chatGPT rocks") == "Chat-GPT-Rocks"


def test_to_path_case():
    assert ts.to_path_case("hello world") == "hello/world"


def test_to_flat_case():
    assert ts.to_flat_case("Hello World") == "helloworld"


def test_to_cobol_case():
    assert ts.to_cobol_case("hello world") == "HELLO-WORLD"


# ── Text cleanup ──────────────────────────────────────────────────────────


def test_remove_extra_spaces_keeps_blank_lines():
    assert ts.remove_extra_spaces("a  b\n\nc  d") == "a b\n\nc d"


def test_remove_all_spaces():
    assert ts.remove_all_spaces("a b\tc\nd e") == "abc\nde"


def test_remove_line_breaks():
    assert ts.remove_line_breaks("a\r\nb\n\nc") == "a b c"


def test_strip_html_removes_tags_and_skips_script():
    html_doc = (
        "<html><head><title>T</title></head>"
        "<body><p>Hello &amp; hi</p><script>var x=1;</script></body></html>"
    )
    assert ts.strip_html(html_doc) == "Hello & hi"


def test_remove_accents():
    assert ts.remove_accents("café naïve") == "cafe naive"


def test_toggle_smart_quotes_straight_to_smart():
    assert ts.toggle_smart_quotes('"hi" it\'s...') == "“hi” it’s…"


def test_toggle_smart_quotes_smart_to_straight():
    assert ts.toggle_smart_quotes("“Hi” ‘there’ —") == "\"Hi\" 'there' --"


def test_toggle_smart_quotes_single_quote_pair():
    assert ts.toggle_smart_quotes("'hi'") == "‘hi’"


def test_strip_invisible():
    assert ts.strip_invisible("a​b") == "ab"


def test_strip_emoji():
    assert ts.strip_emoji("hi 👋 there") == "hi there"


def test_normalize_whitespace_keeps_newlines():
    assert ts.normalize_whitespace("a\t b\nc") == "a b\nc"


def test_strip_non_ascii():
    assert ts.strip_non_ascii("héllo") == "hllo"


def test_fix_line_endings():
    assert ts.fix_line_endings("a\r\nb\rc") == "a\nb\nc"


def test_strip_markdown():
    md = "# Title\n**bold** and *ital* [link](http://x) `code`\n> quote\n- item"
    assert ts.strip_markdown(md) == "Title\nbold and ital link code\nquote\nitem"


def test_trim_lines():
    assert ts.trim_lines("  a  \n b ") == "a\nb"


def test_strip_empty_lines():
    assert ts.strip_empty_lines("a\n\n  \nb") == "a\nb"


def test_strip_urls():
    assert ts.strip_urls("see https://x.com and www.y.com now") == "see and now"


def test_strip_emails():
    assert ts.strip_emails("mail me@x.com now") == "mail now"


def test_normalize_punctuation_spacing():
    assert ts.normalize_punctuation("Hello ,world .End") == "Hello, world. End"


def test_normalize_punctuation_parentheses():
    assert ts.normalize_punctuation("( spaced )") == "(spaced)"


def test_strip_numbers():
    assert ts.strip_numbers("abc 123 def45") == "abc def"


# ── Encoding ──────────────────────────────────────────────────────────────


def test_base64_roundtrip_per_line():
    assert ts.base64_encode("hi\nyo") == "aGk=\neW8="
    assert ts.base64_decode("aGk=\neW8=") == "hi\nyo"


def test_url_encode_decode():
    assert ts.url_encode("a b/c") == "a%20b%2Fc"
    assert ts.url_decode("a%20b") == "a b"


def test_hex_encode_decode():
    assert ts.hex_encode("hi") == "6869"
    assert ts.hex_decode("6869") == "hi"


def test_hex_decode_invalid_raises():
    with pytest.raises(ValueError):
        ts.hex_decode("zz")


def test_morse_encode_decode():
    assert ts.morse_encode("SOS SOS") == "... --- ... / ... --- ..."
    assert ts.morse_decode("... --- ... / ... --- ...") == "SOS SOS"


def test_binary_encode_decode():
    assert ts.binary_encode("hi") == "01101000 01101001"
    assert ts.binary_decode("01101000 01101001") == "hi"


def test_octal_encode_decode():
    assert ts.octal_encode("hi") == "150 151"
    assert ts.octal_decode("150 151") == "hi"


def test_decimal_encode_decode():
    assert ts.decimal_encode("hi") == "104 105"
    assert ts.decimal_decode("104 105") == "hi"


def test_unicode_escape_bmp_and_astral():
    assert ts.unicode_escape("a\U0001d11e") == "\\u0061\\U0001d11e"


def test_unicode_unescape_multiline():
    assert ts.unicode_unescape("\\u0041\n\\u0042") == "A\nB"


def test_base32_encode_decode_without_padding():
    assert ts.base32_encode("hi") == "NBUQ===="
    assert ts.base32_decode("NBUQ") == "hi"


def test_ascii85_roundtrip():
    assert ts.ascii85_encode("hello") == "BOu!rDZ"
    assert ts.ascii85_decode(ts.ascii85_encode("hello")) == "hello"


# ── Brainfuck ─────────────────────────────────────────────────────────────


def test_brainfuck_encode_emits_diffs():
    assert ts.brainfuck_encode("ba") == "+" * 98 + ".-."


def test_brainfuck_roundtrip():
    assert ts.brainfuck_decode(ts.brainfuck_encode("Hi!")) == "Hi!"


def test_brainfuck_decode_loop():
    assert ts.brainfuck_decode("++[>+<-]>.") == "\x02"


def test_brainfuck_decode_cell_wraps_below_zero():
    assert ts.brainfuck_decode("-.") == chr(255)


def test_brainfuck_decode_input_reads_zero():
    assert ts.brainfuck_decode("+,.") == "\x00"


def test_brainfuck_decode_pointer_wraps_both_ways():
    assert ts.brainfuck_decode("<+.") == "\x01"
    assert ts.brainfuck_decode(">" * 30000 + "+.") == "\x01"


def test_brainfuck_decode_unmatched_brackets():
    with pytest.raises(ValueError, match=r"Unmatched '\]'"):
        ts.brainfuck_decode("+]")
    with pytest.raises(ValueError, match=r"Unmatched '\['"):
        ts.brainfuck_decode("[+")


# ── Ciphers ───────────────────────────────────────────────────────────────


def test_atbash_cipher():
    assert ts.atbash_cipher("abz ABZ!") == "zya ZYA!"


def test_caesar_cipher_wraps_alphabet():
    assert ts.caesar_cipher("xyz", 3) == "abc"
    assert ts.caesar_cipher("XYZ", 3) == "ABC"
    assert ts.caesar_cipher("abc") == "def"  # default shift=3


def test_caesar_brute_force_single_line():
    result = ts.caesar_brute_force("bcd")
    lines = result.splitlines()
    assert len(lines) == 25
    assert lines[0] == "Shift  1: abc"


def test_caesar_brute_force_multiline_blocks():
    result = ts.caesar_brute_force("b\nc")
    assert "\n\n" in result
    assert len(result.splitlines()) == 51  # 25 + blank + 25


def test_vigenere_encrypt_decrypt():
    assert ts.vigenere_encrypt("ATTACKATDAWN", "LEMON") == "LXFOPVEFRNHR"
    assert ts.vigenere_decrypt("LXFOPVEFRNHR", "LEMON") == "ATTACKATDAWN"


def test_vigenere_skips_non_letters():
    assert ts.vigenere_encrypt("ab cd", "b") == "bc de"


def test_vigenere_invalid_key_raises():
    with pytest.raises(ValueError):
        ts.vigenere_encrypt("abc", "123")
    with pytest.raises(ValueError):
        ts.vigenere_decrypt("abc", "")


def test_rail_fence_encrypt_classic():
    assert (
        ts.rail_fence_encrypt("WEAREDISCOVEREDFLEEATONCE", 3)
        == "WECRLTEERDSOEEFEAOCAIVDEN"
    )


def test_rail_fence_decrypt_roundtrip():
    encrypted = ts.rail_fence_encrypt("HELLOWORLD", 4)
    assert ts.rail_fence_decrypt(encrypted, 4) == "HELLOWORLD"


def test_rail_fence_multiline_per_line():
    assert ts.rail_fence_encrypt("abc\ndef", 2) == "acb\ndfe"
    assert ts.rail_fence_decrypt("acb\ndfe", 2) == "abc\ndef"


def test_rail_fence_rails_below_two_raises():
    with pytest.raises(ValueError):
        ts.rail_fence_encrypt("abc", 1)
    with pytest.raises(ValueError):
        ts.rail_fence_decrypt("abc", 1)


def test_playfair_encrypt_classic():
    assert (
        ts.playfair_encrypt("hide the gold in the tree stump", "playfair example")
        == "BMODZBXDNABEKUDMUIXMMOUVIF"
    )


def test_playfair_encrypt_multiline():
    result = ts.playfair_encrypt("hi\nhi", "key")
    lines = result.splitlines()
    assert len(lines) == 2
    assert lines[0] == lines[1]


def test_playfair_empty_key_raises():
    with pytest.raises(ValueError):
        ts.playfair_encrypt("hello", "")


def test_substitution_cipher_both_cases():
    mapping = "QWERTYUIOPASDFGHJKLZXCVBNM"
    assert ts.substitution_cipher("abc ABC!", mapping) == "qwe QWE!"


def test_substitution_cipher_bad_mapping_raises():
    with pytest.raises(ValueError):
        ts.substitution_cipher("abc", "SHORT")


def test_columnar_transposition():
    assert ts.columnar_transposition("HELLOWORLD", "KEY") == "EOR HLODLWL "


def test_columnar_transposition_multiline():
    assert ts.columnar_transposition("ab\ncd", "ba") == "ba\ndc"


def test_columnar_transposition_empty_key_raises():
    with pytest.raises(ValueError):
        ts.columnar_transposition("abc", "")


def test_nato_phonetic_forward():
    assert ts.nato_phonetic("ab 1") == "Alpha Bravo [space] One"


def test_nato_phonetic_reverse():
    assert ts.nato_phonetic("Alpha Bravo") == "AB"


def test_nato_phonetic_multiline():
    assert ts.nato_phonetic("a\nb") == "Alpha\nBravo"


def test_bacon_cipher_encode_and_decode():
    encoded = ts.bacon_cipher("HELLO")
    assert set(encoded) <= {"A", "B", " "}
    assert ts.bacon_cipher(encoded) == "HELLO"


def test_bacon_cipher_short_ab_input_is_encoded_not_decoded():
    assert ts.bacon_cipher("AB") == "AAAAA AAAAB"


def test_bacon_cipher_multiline():
    assert ts.bacon_cipher("a\nb") == "AAAAA\nAAAAB"


def test_rot13():
    assert ts.rot13("Hello") == "Uryyb"


# ── Text tools ────────────────────────────────────────────────────────────


def test_reverse_text():
    assert ts.reverse_text("abc") == "cba"


def test_sort_lines_case_insensitive():
    assert ts.sort_lines_asc("banana\nApple\ncherry") == "Apple\nbanana\ncherry"
    assert ts.sort_lines_desc("banana\nApple\ncherry") == "cherry\nbanana\nApple"


def test_reverse_lines():
    assert ts.reverse_lines("a\nb\nc") == "c\nb\na"


def test_number_lines():
    assert ts.number_lines("a\nb") == "1. a\n2. b"


def test_remove_duplicate_lines():
    assert ts.remove_duplicate_lines("a\nb\na") == "a\nb"


def test_shuffle_lines_preserves_content():
    result = ts.shuffle_lines("a\nb\nc\nd")
    assert sorted(result.splitlines()) == ["a", "b", "c", "d"]


def test_sort_by_length():
    assert ts.sort_by_length("aaa\na\naa") == "a\naa\naaa"


def test_sort_numeric_puts_non_numeric_last():
    assert ts.sort_numeric("item 10\nitem 2\nnone") == "item 2\nitem 10\nnone"


def test_line_frequency():
    assert ts.line_frequency("a\nb\na") == "2x  a\n1x  b"


def test_split_to_lines():
    assert ts.split_to_lines("a, b,c", ",") == "a\nb\nc"
    assert ts.split_to_lines("x,y") == "x\ny"  # default delimiter


def test_join_lines_skips_blank_lines():
    assert ts.join_lines("a\n b \n\nc", "-") == "a-b-c"


def test_pad_lines_alignments():
    assert ts.pad_lines("a\nbbb") == "a  \nbbb"
    assert ts.pad_lines("a\nbbb", "right") == "  a\nbbb"
    assert ts.pad_lines("a\nbbb", "center") == " a \nbbb"


def test_wrap_lines():
    assert ts.wrap_lines("a\nb", prefix="<", suffix=">") == "<a>\n<b>"


def test_truncate_lines():
    assert ts.truncate_lines("abcdef\nab", max_length=5) == "abcd…\nab"


def test_extract_nth_lines():
    assert ts.extract_nth_lines("a\nb\nc\nd\ne", n=2, offset=0) == "a\nc\ne"
    assert ts.extract_nth_lines("a\nb\nc\nd\ne", n=2, offset=1) == "b\nd"


# ── Line filtering / matching ─────────────────────────────────────────────


def test_filter_lines_contain_substring():
    text = "Apple\nbanana\ncherry"
    assert ts.filter_lines_contain(text, "an") == "banana"
    assert ts.filter_lines_contain("Apple\napple", "apple", case_sensitive=True) == (
        "apple"
    )


def test_remove_lines_contain_substring():
    assert ts.remove_lines_contain("Apple\nbanana", "an") == "Apple"


def test_filter_lines_regex_with_timeout_capable_pattern():
    pat = regex.compile("^a", regex.IGNORECASE)
    assert (
        ts.filter_lines_contain("Apple\nbanana", "^a", use_regex=True, compiled=pat)
        == "Apple"
    )


def test_filter_lines_regex_stdlib_pattern_fallback():
    # stdlib re.Pattern.search() has no timeout kwarg - the TypeError fallback
    # path must still match correctly.
    pat = re.compile("^a")
    assert (
        ts.filter_lines_contain("apple\nbanana", "^a", use_regex=True, compiled=pat)
        == "apple"
    )


def test_filter_lines_regex_without_compiled_matches_nothing():
    assert ts.filter_lines_contain("apple", "^a", use_regex=True, compiled=None) == ""


def test_filter_lines_regex_caps_line_length():
    # Match target sits beyond the 2000-char search window - not found.
    pat = regex.compile("z$")
    long_line = "b" * 2500 + "z"
    assert ts.filter_lines_contain(long_line, "z$", use_regex=True, compiled=pat) == ""


def test_filter_lines_regex_timeout_raises():
    class _TimeoutPattern:
        def search(self, *_a, **_k):
            raise TimeoutError("too slow")

    with pytest.raises(ts.RegexTimeoutError, match="budget"):
        ts.filter_lines_contain(
            "aaaa", "(a+)+$", use_regex=True, compiled=_TimeoutPattern()
        )


# ── Developer tools ───────────────────────────────────────────────────────


def test_format_json():
    result = ts.format_json('{"b":1,"a":2}')
    assert result == '{\n  "b": 1,\n  "a": 2\n}'


def test_json_to_yaml():
    result = ts.json_to_yaml('{"a": 1, "b": [1, 2]}')
    assert yaml.safe_load(result) == {"a": 1, "b": [1, 2]}


def test_json_escape():
    assert ts.json_escape('he said "hi"\nline2') == 'he said \\"hi\\"\nline2'


def test_json_unescape():
    assert ts.json_unescape('he said \\"hi\\"') == 'he said "hi"'


def test_html_escape_and_unescape():
    assert ts.html_escape_text('<a href="x">&</a>') == (
        "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"
    )
    assert ts.html_unescape_text("&lt;b&gt;") == "<b>"


def test_csv_to_json():
    assert json.loads(ts.csv_to_json("a,b\n1,2")) == [{"a": "1", "b": "2"}]


def test_json_to_csv():
    result = ts.json_to_csv('[{"a": 1, "b": "x"}]')
    assert "a,b" in result
    assert "1,x" in result


def test_json_to_csv_rejects_non_array():
    with pytest.raises(ValueError):
        ts.json_to_csv("{}")
    with pytest.raises(ValueError):
        ts.json_to_csv("[]")


def test_xml_to_json_lists_attrs_and_text():
    result = ts.xml_to_json('<root><a>1</a><a>2</a><b x="y">t</b></root>')
    assert json.loads(result) == {
        "root": {"a": ["1", "2"], "b": {"@x": "y", "#text": "t"}}
    }


def test_xml_to_json_empty_leaf():
    assert json.loads(ts.xml_to_json("<r/>")) == {"r": None}


def test_xml_to_json_mixed_text_and_children():
    result = ts.xml_to_json("<r>hi<c>1</c></r>")
    assert json.loads(result) == {"r": {"c": "1", "#text": "hi"}}


def test_xml_to_json_multiple_roots():
    result = ts.xml_to_json("<a>1</a><b>2</b>")
    assert result == '{\n  "a": "1"\n}\n\n{\n  "b": "2"\n}'


def test_xml_to_json_invalid_raises():
    with pytest.raises(ValueError, match="Invalid XML"):
        ts.xml_to_json("not xml <")


def test_csv_to_table():
    assert ts.csv_to_table("h1,h2\naa,b") == ("| h1 | h2 |\n| -- | -- |\n| aa | b  |")


def test_csv_to_table_empty_input_passthrough():
    assert ts.csv_to_table("") == ""


def test_sql_insert_gen_quotes_and_numbers():
    assert ts.sql_insert_gen("name,age\nBob,30\nO'Neil,x") == (
        "INSERT INTO table_name (name, age) VALUES ('Bob', 30);\n"
        "INSERT INTO table_name (name, age) VALUES ('O''Neil', 'x');"
    )


def test_sql_insert_gen_requires_data_row():
    with pytest.raises(ValueError):
        ts.sql_insert_gen("only,header")
