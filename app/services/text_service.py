"""
Local text transformation functions.

All functions are pure and synchronous.  The API layer wraps them in
``asyncio.to_thread()`` to avoid blocking the event loop.  Adding a
new local tool only requires writing the function here and registering
it in ``app.core.tool_registry``.
"""

import base64
import codecs
import csv
import html
import io
import json
import re
import unicodedata
from urllib.parse import quote, unquote

import yaml

# Hard wall-clock cap for a single user-supplied regex search. Patterns that
# blow past this are assumed to be ReDoS (intentional or accidental) and the
# request is rejected.
USER_REGEX_TIMEOUT_S = 0.2


class RegexTimeoutError(Exception):
    """Raised when a user-supplied regex exceeds USER_REGEX_TIMEOUT_S."""


# ── Case transformations ──────────────────────────────────────────────────
#
# Many of these tools collapse internal whitespace/punctuation into a
# tool-specific separator (e.g. snake_case turns spaces into '_'). When
# applied naively to multi-line input they collapse `\n` into the same
# separator, fusing all lines into one. That's almost never what users
# want — each line should be transformed as its own independent string.
#
# `_per_line` enforces that uniformly: split on '\n' (NOT generic
# whitespace, which is what `text.split()` would do), run the inner
# single-line transform on each line, rejoin with '\n'. Empty lines stay
# empty so user-authored blank lines are preserved.


def _per_line(transform):
    """Wrap a single-line transform so it processes each line independently."""

    def wrapped(text: str) -> str:
        if "\n" not in text:
            return transform(text)
        return "\n".join(transform(line) for line in text.split("\n"))

    return wrapped


def to_uppercase(text: str) -> str:
    return text.upper()


def to_lowercase(text: str) -> str:
    return text.lower()


def to_inverse_case(text: str) -> str:
    return "".join(c.lower() if c.isupper() else c.upper() for c in text)


def _sentence_case_line(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    # Preserve the original trailing punctuation (if any).
    trailing = text[-1] if text[-1] in ".?!" else ""
    if text.endswith((".", "?", "!")):
        text = text[:-1]
    sentences = re.split(r"[.?!]\s*(?=\S|$)", text)
    result = ". ".join(s.strip().capitalize() for s in sentences if s.strip())
    return result + (trailing or ".")


def _title_case_line(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())


to_sentence_case = _per_line(_sentence_case_line)
to_title_case = _per_line(_title_case_line)


def _split_identifier_words(text: str) -> list[str]:
    """Split a single line into identifier words.

    Recognises three boundary kinds, in order:

    1. Any non-alphanumeric run (``hello world``, ``foo_bar``, ``a-b.c``).
    2. lowercase/digit → uppercase (``camelCase`` → ``camel`` + ``Case``).
    3. Acronym boundary: uppercase followed by uppercase-then-lowercase
       (``XMLHttp`` → ``XML`` + ``Http``, ``ChatGPT`` → ``Chat`` + ``GPT``).

    The acronym rule is what makes ``ChatGPT`` come out as ``[Chat, GPT]``
    instead of ``[ChatGPT]`` — without it, train-case / snake-case can't
    distinguish ``GPT`` as its own word.
    """
    # Insert a sentinel `\x00` at every word boundary, then split on it +
    # any other non-alphanumeric run. Using a sentinel keeps the two
    # boundary regexes simple and order-independent.
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "\x00", text)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "\x00", s)
    return [w for w in re.split(r"[^a-zA-Z0-9]+|\x00", s) if w]


def _smart_capitalize(word: str) -> str:
    """Capitalize a word, preserving runs of all-uppercase letters as-is.

    ``GPT`` → ``GPT`` (acronym preserved). ``hello`` → ``Hello``.
    ``HELLO`` → ``HELLO`` (already an acronym). ``hELLO`` → ``Hello``
    (mixed case is normalised since the caller likely typed garbage).
    """
    if not word:
        return word
    if word.isupper():
        return word
    return word[0].upper() + word[1:].lower()


def _upper_camel_case_line(text: str) -> str:
    return "".join(_smart_capitalize(w) for w in _split_identifier_words(text))


def _lower_camel_case_line(text: str) -> str:
    words = _split_identifier_words(text)
    if not words:
        return ""
    # First word is fully lowercase; the rest follow PascalCase rules
    # (preserving acronyms via _smart_capitalize).
    return words[0].lower() + "".join(_smart_capitalize(w) for w in words[1:])


def _snake_case_line(text: str) -> str:
    return "_".join(w.lower() for w in _split_identifier_words(text))


def _kebab_case_line(text: str) -> str:
    return "-".join(w.lower() for w in _split_identifier_words(text))


to_upper_camel_case = _per_line(_upper_camel_case_line)
to_lower_camel_case = _per_line(_lower_camel_case_line)
to_snake_case = _per_line(_snake_case_line)
to_kebab_case = _per_line(_kebab_case_line)


def _capitalize_words_line(text: str) -> str:
    return " ".join(w[0].upper() + w[1:] if w else w for w in text.split(" "))


to_capitalize_words = _per_line(_capitalize_words_line)


def to_alternating_case(text: str) -> str:
    result = []
    i = 0
    for c in text:
        if c.isalpha():
            result.append(c.lower() if i % 2 == 0 else c.upper())
            i += 1
        else:
            result.append(c)
    return "".join(result)


def _inverse_word_case_line(text: str) -> str:
    result = []
    for word in text.split(" "):
        if word:
            result.append(
                word[:-1].lower() + word[-1].upper() if len(word) > 1 else word.upper()
            )
        else:
            result.append(word)
    return " ".join(result)


def _wide_text_line(text: str) -> str:
    return " ".join(text)


to_inverse_word_case = _per_line(_inverse_word_case_line)
to_wide_text = _per_line(_wide_text_line)


_SMALL_CAPS_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ",
)


def to_small_caps(text: str) -> str:
    return text.lower().translate(_SMALL_CAPS_MAP)


_UPSIDE_DOWN_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?'\"",
    "ɐqɔpǝɟƃɥᴉɾʞlɯuodbɹsʇnʌʍxʎz∀qƆpƎℲפHIſʞ˥WNOԀQɹS┴∩ΛMX⅄Z0ƖᄅƐㄣϛ9ㄥ86˙'¡¿,„",
)


def to_upside_down(text: str) -> str:
    return text.translate(_UPSIDE_DOWN_MAP)[::-1]


def to_strikethrough(text: str) -> str:
    lines = text.split("\n")
    return "\n".join(f"<del>{line}</del>" if line.strip() else line for line in lines)


# AP-style small words that should stay lowercase in titles
_AP_SMALL_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "if",
    "in",
    "nor",
    "of",
    "on",
    "or",
    "so",
    "the",
    "to",
    "up",
    "yet",
    "is",
    "it",
    "its",
    "my",
    "vs",
    "via",
}


def _ap_title_case_line(text: str) -> str:
    words = text.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or i == len(words) - 1 or w.lower() not in _AP_SMALL_WORDS:
            result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)


def _swap_word_case_line(text: str) -> str:
    words = text.split(" ")
    result = []
    for i, w in enumerate(words):
        result.append(w.upper() if i % 2 == 0 else w.lower())
    return " ".join(result)


to_ap_title_case = _per_line(_ap_title_case_line)
to_swap_word_case = _per_line(_swap_word_case_line)


def _dot_case_line(text: str) -> str:
    return ".".join(w.lower() for w in _split_identifier_words(text))


def _constant_case_line(text: str) -> str:
    return "_".join(w.upper() for w in _split_identifier_words(text))


def _train_case_line(text: str) -> str:
    # Train-Case = HTTP-Header-Case: each word capitalised (or preserved as
    # acronym), joined with '-'. ``ChatGPT`` → ``Chat-GPT`` because GPT is
    # detected as an acronym word and kept as-is.
    return "-".join(_smart_capitalize(w) for w in _split_identifier_words(text))


def _path_case_line(text: str) -> str:
    return "/".join(w.lower() for w in _split_identifier_words(text))


def _flat_case_line(text: str) -> str:
    # All collapsed into a single lowercase token — no acronym preservation
    # because the convention IS to be flat (e.g. ``chatgpt``).
    return "".join(w.lower() for w in _split_identifier_words(text))


def _cobol_case_line(text: str) -> str:
    return "-".join(w.upper() for w in _split_identifier_words(text))


to_dot_case = _per_line(_dot_case_line)
to_constant_case = _per_line(_constant_case_line)
to_train_case = _per_line(_train_case_line)
to_path_case = _per_line(_path_case_line)
to_flat_case = _per_line(_flat_case_line)
to_cobol_case = _per_line(_cobol_case_line)


# ── Text Cleanup ──────────────────────────────────────────────────────────


remove_extra_spaces = _per_line(lambda s: " ".join(s.split()))
remove_all_spaces = _per_line(lambda s: re.sub(r"[ \t\f\v]+", "", s))


def remove_line_breaks(text: str) -> str:
    return re.sub(r"[\r\n]+", " ", text).strip()


def strip_html(text: str) -> str:
    from html.parser import HTMLParser

    class _TagStripper(HTMLParser):
        _skip = frozenset(("head", "style", "script", "noscript"))

        def __init__(self):
            super().__init__()
            self._fed: list[str] = []
            self._skip_depth = 0

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag.lower() in self._skip:
                self._skip_depth += 1

        def handle_endtag(self, tag: str) -> None:
            if tag.lower() in self._skip and self._skip_depth > 0:
                self._skip_depth -= 1

        def handle_data(self, data: str) -> None:
            if self._skip_depth == 0:
                self._fed.append(data)

        def get_text(self) -> str:
            return "".join(self._fed)

    stripper = _TagStripper()
    stripper.feed(text)
    clean = html.unescape(stripper.get_text())
    clean = re.sub(r"\n\s*\n+", "\n\n", clean).strip()
    return clean


def remove_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def toggle_smart_quotes(text: str) -> str:
    has_smart = any(c in text for c in "\u2018\u2019\u201c\u201d")
    if has_smart:
        for smart, straight in {
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\u2013": "-",
            "\u2014": "--",
            "\u2026": "...",
        }.items():
            text = text.replace(smart, straight)
    else:
        result = []
        open_double = True
        for ch in text:
            if ch == '"':
                result.append("\u201c" if open_double else "\u201d")
                open_double = not open_double
            else:
                result.append(ch)
        text = "".join(result)
        result = []
        open_single = True
        for i, ch in enumerate(text):
            if ch == "'":
                if (
                    i > 0
                    and i < len(text) - 1
                    and text[i - 1].isalpha()
                    and text[i + 1].isalpha()
                ):
                    result.append("\u2019")
                else:
                    result.append("\u2018" if open_single else "\u2019")
                    open_single = not open_single
            else:
                result.append(ch)
        text = "".join(result)
        text = text.replace("...", "\u2026")
        text = re.sub(r"(?<!-)--(?!-)", "\u2014", text)
    return text


def strip_invisible(text: str) -> str:
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def strip_emoji(text: str) -> str:
    import emoji

    cleaned = emoji.replace_emoji(text, replace="")
    return re.sub(r"  +", " ", cleaned).strip()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"[^\S\n]+", " ", text)


def strip_non_ascii(text: str) -> str:
    return re.sub(r"[^\x00-\x7F]", "", text)


def fix_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_markdown(text: str) -> str:
    s = text
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"!\[([^\[\]]*)\]\(([^()]*)\)", r"\1", s)
    s = re.sub(r"\[([^\[\]]*)\]\(([^()]*)\)", r"\1", s)
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
    s = re.sub(r"__(.*?)__", r"\1", s)
    s = re.sub(r"\*(.*?)\*", r"\1", s)
    s = re.sub(r"_(.*?)_", r"\1", s)
    s = re.sub(r"~~(.*?)~~", r"\1", s)
    s = re.sub(r"`{3}[\s\S]*?`{3}", "", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"^>\s?", "", s, flags=re.MULTILINE)
    s = re.sub(r"^[-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\d+\.\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^[-*_]{3,}\s*$", "", s, flags=re.MULTILINE)
    return s.strip()


def trim_lines(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines())


def strip_empty_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if line.strip())


def strip_urls(text: str) -> str:
    s = re.sub(r"https?://\S+", "", text)
    s = re.sub(r"www\.\S+", "", s)
    return re.sub(r"  +", " ", s).strip()


def strip_emails(text: str) -> str:
    # Remove whitespace-delimited tokens that contain "@".
    # Token-based approach avoids polynomial regex backtracking on user input.
    cleaned = " ".join(t for t in text.split() if "@" not in t)
    return re.sub(r"  +", " ", cleaned).strip()


_WS = frozenset(" \t\n\r")
_PUNCT_CLOSE = frozenset(".,;:!?)")


def normalize_punctuation(text: str) -> str:
    # Linear-scan approach instead of re.sub with `+` quantifiers, which can
    # exhibit O(n²) behavior on user-provided strings.

    # Pass 1: strip whitespace immediately before ".,;:!?" and ")"
    # and immediately after "(".
    buf: list[str] = []
    skip_open_ws = False
    for ch in text:
        if ch in _PUNCT_CLOSE:
            while buf and buf[-1] in _WS:
                buf.pop()
        if skip_open_ws and ch in _WS:
            continue
        skip_open_ws = ch == "("
        buf.append(ch)

    s = "".join(buf)
    s = re.sub(r"([.,;:!?])([^\s.,;:!?\'\"\)\]\}0-9])", r"\1 \2", s)
    s = re.sub(r"\.{2}(?!\.)", ".", s)
    return s


def strip_numbers(text: str) -> str:
    s = re.sub(r"\d+", "", text)
    return re.sub(r"  +", " ", s).strip()


# ── Encoding ──────────────────────────────────────────────────────────────


base64_encode = _per_line(lambda s: base64.b64encode(s.encode("utf-8")).decode("utf-8"))
base64_decode = _per_line(lambda s: base64.b64decode(s.encode("utf-8")).decode("utf-8"))

url_encode = _per_line(lambda s: quote(s, safe=""))
url_decode = _per_line(unquote)

hex_encode = _per_line(lambda s: s.encode("utf-8").hex())
hex_decode = _per_line(lambda s: bytes.fromhex(s.strip()).decode("utf-8"))


# ── Morse Code ─────────────────────────────────────────────────────────────

_MORSE_MAP = {
    "A": ".-",
    "B": "-...",
    "C": "-.-.",
    "D": "-..",
    "E": ".",
    "F": "..-.",
    "G": "--.",
    "H": "....",
    "I": "..",
    "J": ".---",
    "K": "-.-",
    "L": ".-..",
    "M": "--",
    "N": "-.",
    "O": "---",
    "P": ".--.",
    "Q": "--.-",
    "R": ".-.",
    "S": "...",
    "T": "-",
    "U": "..-",
    "V": "...-",
    "W": ".--",
    "X": "-..-",
    "Y": "-.--",
    "Z": "--..",
    "0": "-----",
    "1": ".----",
    "2": "..---",
    "3": "...--",
    "4": "....-",
    "5": ".....",
    "6": "-....",
    "7": "--...",
    "8": "---..",
    "9": "----.",
    ".": ".-.-.-",
    ",": "--..--",
    "?": "..--..",
    "'": ".----.",
    "!": "-.-.--",
    "/": "-..-.",
    "(": "-.--.",
    ")": "-.--.-",
    "&": ".-...",
    ":": "---...",
    ";": "-.-.-.",
    "=": "-...-",
    "+": ".-.-.",
    "-": "-....-",
    "_": "..--.-",
    '"': ".-..-.",
    "$": "...-..-",
    "@": ".--.-.",
}
_MORSE_REVERSE = {v: k for k, v in _MORSE_MAP.items()}


def _morse_encode_line(text: str) -> str:
    result = []
    for ch in text.upper():
        if ch == " ":
            result.append("/")
        elif ch in _MORSE_MAP:
            result.append(_MORSE_MAP[ch])
    return " ".join(result)


def _morse_decode_line(text: str) -> str:
    words = text.strip().split(" / ")
    decoded = []
    for word in words:
        letters = word.strip().split()
        decoded.append("".join(_MORSE_REVERSE.get(c, "") for c in letters))
    return " ".join(decoded)


morse_encode = _per_line(_morse_encode_line)
morse_decode = _per_line(_morse_decode_line)


# ── Text Tools ────────────────────────────────────────────────────────────


def reverse_text(text: str) -> str:
    return text[::-1]


def sort_lines_asc(text: str) -> str:
    return "\n".join(sorted(text.splitlines(), key=str.casefold))


def sort_lines_desc(text: str) -> str:
    return "\n".join(sorted(text.splitlines(), key=str.casefold, reverse=True))


def reverse_lines(text: str) -> str:
    return "\n".join(text.splitlines()[::-1])


def number_lines(text: str) -> str:
    return "\n".join(f"{i}. {line}" for i, line in enumerate(text.splitlines(), 1))


def rot13(text: str) -> str:
    return codecs.encode(text, "rot_13")


# ── Binary / Octal / Decimal Encoding ───────────────────────────────────


binary_encode = _per_line(
    lambda s: " ".join(format(b, "08b") for b in s.encode("utf-8"))
)
binary_decode = _per_line(
    lambda s: bytes(int(b, 2) for b in s.strip().split()).decode("utf-8")
)

octal_encode = _per_line(
    lambda s: " ".join(format(b, "03o") for b in s.encode("utf-8"))
)
octal_decode = _per_line(
    lambda s: bytes(int(o, 8) for o in s.strip().split()).decode("utf-8")
)

decimal_encode = _per_line(lambda s: " ".join(str(b) for b in s.encode("utf-8")))
decimal_decode = _per_line(
    lambda s: bytes(int(d) for d in s.strip().split()).decode("utf-8")
)


# ── Brainfuck Encoding ──────────────────────────────────────────────────


def _brainfuck_encode_line(text: str) -> str:
    """Convert a single line to a Brainfuck program that prints it."""
    result = []
    prev = 0
    for ch in text:
        val = ord(ch)
        diff = val - prev
        if diff > 0:
            result.append("+" * diff)
        elif diff < 0:
            result.append("-" * (-diff))
        result.append(".")
        prev = val
    return "".join(result)


brainfuck_encode = _per_line(_brainfuck_encode_line)


def brainfuck_decode(code: str) -> str:
    """Execute a Brainfuck program and return its output."""
    tape = [0] * 30000
    ptr = 0
    ip = 0
    output = []
    # Pre-compute bracket pairs
    stack = []
    brackets = {}
    for i, ch in enumerate(code):
        if ch == "[":
            stack.append(i)
        elif ch == "]":
            if not stack:
                raise ValueError(f"Unmatched ']' at position {i}")
            j = stack.pop()
            brackets[j] = i
            brackets[i] = j
    if stack:
        raise ValueError(f"Unmatched '[' at position {stack[-1]}")

    max_steps = 10_000_000  # prevent infinite loops
    steps = 0
    while ip < len(code):
        steps += 1
        if steps > max_steps:
            raise ValueError(
                "Execution exceeded maximum step limit (possible infinite loop)"
            )
        ch = code[ip]
        if ch == ">":
            ptr += 1
            if ptr >= 30000:
                ptr = 0
        elif ch == "<":
            ptr -= 1
            if ptr < 0:
                ptr = 29999
        elif ch == "+":
            tape[ptr] = (tape[ptr] + 1) % 256
        elif ch == "-":
            tape[ptr] = (tape[ptr] - 1) % 256
        elif ch == ".":
            output.append(chr(tape[ptr]))
        elif ch == ",":
            tape[ptr] = 0  # no input available
        elif ch == "[":
            if tape[ptr] == 0:
                ip = brackets[ip]
        elif ch == "]":
            if tape[ptr] != 0:
                ip = brackets[ip]
        ip += 1
    return "".join(output)


# ── Unicode Escape / Unescape ───────────────────────────────────────────


def _unicode_escape_line(line: str) -> str:
    return "".join(
        f"\\u{ord(ch):04x}" if ord(ch) <= 0xFFFF else f"\\U{ord(ch):08x}" for ch in line
    )


def unicode_escape(text: str) -> str:
    return "\n".join(_unicode_escape_line(line) for line in text.split("\n"))


def unicode_unescape(text: str) -> str:
    return "\n".join(
        line.encode("utf-8").decode("unicode_escape") for line in text.split("\n")
    )


# ── Ciphers ─────────────────────────────────────────────────────────────


def atbash_cipher(text: str) -> str:
    result = []
    for ch in text:
        if "a" <= ch <= "z":
            result.append(chr(ord("z") - (ord(ch) - ord("a"))))
        elif "A" <= ch <= "Z":
            result.append(chr(ord("Z") - (ord(ch) - ord("A"))))
        else:
            result.append(ch)
    return "".join(result)


def remove_duplicate_lines(text: str) -> str:
    seen: set = set()
    result = []
    for line in text.splitlines():
        if line not in seen:
            seen.add(line)
            result.append(line)
    return "\n".join(result)


def shuffle_lines(text: str) -> str:
    import random

    lines = text.splitlines()
    random.shuffle(lines)
    return "\n".join(lines)


def sort_by_length(text: str) -> str:
    return "\n".join(sorted(text.splitlines(), key=len))


def sort_numeric(text: str) -> str:
    def _numeric_key(line: str):
        match = re.search(r"-?\d+\.?\d*", line)
        return float(match.group()) if match else float("inf")

    return "\n".join(sorted(text.splitlines(), key=_numeric_key))


def line_frequency(text: str) -> str:
    from collections import Counter

    counts = Counter(text.splitlines())
    return "\n".join(f"{count}x  {line}" for line, count in counts.most_common())


def split_to_lines(text: str, delimiter: str = ",") -> str:
    return "\n".join(part.strip() for part in text.split(delimiter))


def join_lines(text: str, separator: str = ", ") -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return separator.join(lines)


def pad_lines(text: str, align: str = "left") -> str:
    lines = text.splitlines()
    max_len = max((len(line) for line in lines), default=0)
    if align == "right":
        return "\n".join(line.rjust(max_len) for line in lines)
    elif align == "center":
        return "\n".join(line.center(max_len) for line in lines)
    return "\n".join(line.ljust(max_len) for line in lines)


def wrap_lines(text: str, prefix: str = "", suffix: str = "") -> str:
    return "\n".join(f"{prefix}{line}{suffix}" for line in text.splitlines())


def _line_matches(
    line: str,
    pattern: str,
    case_sensitive: bool,
    use_regex: bool,
    compiled: "re.Pattern[str] | None" = None,
) -> bool:
    """Match a line against a pattern.

    When use_regex=True, *compiled* must be a pre-compiled Pattern produced by
    the schema validator (FilterRequest._compile_regex).  Passing the compiled
    object instead of the raw user string ensures that no user-controlled value
    is ever handed directly to re.compile inside this function.
    """
    if use_regex:
        if compiled is None:
            return False
        # Cap line length to limit worst-case backtracking on large inputs.
        search_text = line if len(line) <= 2_000 else line[:2_000]
        # Per-call wall-clock cap. Patterns produced by FilterRequest are
        # `regex.Pattern` objects whose .search() accepts a `timeout=`
        # argument — this is the ReDoS guard. Stdlib `re.Pattern` objects
        # (used by older internal callers and some tests) don't accept
        # `timeout=`, so we fall back to plain .search() for those.
        try:
            return bool(compiled.search(search_text, timeout=USER_REGEX_TIMEOUT_S))
        except TypeError:
            # stdlib re.Pattern — no timeout support; trust the 200-char
            # pattern cap + 2000-char line cap to bound runtime.
            return bool(compiled.search(search_text))
        except TimeoutError as exc:
            raise RegexTimeoutError(
                f"Pattern execution exceeded {int(USER_REGEX_TIMEOUT_S * 1000)}ms "
                "budget — try simplifying or removing nested quantifiers."
            ) from exc
    if case_sensitive:
        return pattern in line
    return pattern.lower() in line.lower()


def filter_lines_contain(
    text: str,
    pattern: str,
    case_sensitive: bool = False,
    use_regex: bool = False,
    compiled: "re.Pattern[str] | None" = None,
) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if _line_matches(line, pattern, case_sensitive, use_regex, compiled)
    )


def remove_lines_contain(
    text: str,
    pattern: str,
    case_sensitive: bool = False,
    use_regex: bool = False,
    compiled: "re.Pattern[str] | None" = None,
) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not _line_matches(line, pattern, case_sensitive, use_regex, compiled)
    )


def truncate_lines(text: str, max_length: int = 80) -> str:
    result = []
    for line in text.splitlines():
        if len(line) > max_length:
            result.append(line[: max_length - 1] + "…")
        else:
            result.append(line)
    return "\n".join(result)


def extract_nth_lines(text: str, n: int = 2, offset: int = 0) -> str:
    lines = text.splitlines()
    return "\n".join(lines[i] for i in range(offset, len(lines), n))


# ── Developer Tools ───────────────────────────────────────────────────────


def format_json(text: str) -> str:
    return json.dumps(json.loads(text), indent=2, ensure_ascii=False)


def json_to_yaml(text: str) -> str:
    return yaml.dump(json.loads(text), allow_unicode=True, default_flow_style=False)


# ── Escape / Unescape ────────────────────────────────────────────────────


def json_escape(text: str) -> str:
    return "\n".join(json.dumps(line)[1:-1] for line in text.split("\n"))


def json_unescape(text: str) -> str:
    return "\n".join(json.loads('"' + line + '"') for line in text.split("\n"))


def html_escape_text(text: str) -> str:
    return html.escape(text, quote=True)


def html_unescape_text(text: str) -> str:
    return html.unescape(text)


# ── CSV / JSON Conversion ────────────────────────────────────────────────


def csv_to_json(text: str) -> str:
    reader = csv.DictReader(io.StringIO(text))
    return json.dumps(list(reader), indent=2, ensure_ascii=False)


def json_to_csv(text: str) -> str:
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        raise ValueError("Input must be a non-empty JSON array")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


# ── Cipher Functions (new) ──────────────────────────────────────────────


def caesar_cipher(text: str, shift: int = 3) -> str:
    result = []
    for ch in text:
        if "a" <= ch <= "z":
            result.append(chr((ord(ch) - ord("a") + shift) % 26 + ord("a")))
        elif "A" <= ch <= "Z":
            result.append(chr((ord(ch) - ord("A") + shift) % 26 + ord("A")))
        else:
            result.append(ch)
    return "".join(result)


def _caesar_brute_force_line(text: str) -> str:
    lines = []
    for shift in range(1, 26):
        decrypted = caesar_cipher(text, -shift)
        lines.append(f"Shift {shift:2d}: {decrypted}")
    return "\n".join(lines)


def caesar_brute_force(text: str) -> str:
    if "\n" not in text:
        return _caesar_brute_force_line(text)
    # Separate each input line's brute-force block with a blank line so the 25
    # shift rows for line N don't visually run into line N+1's rows.
    return "\n\n".join(_caesar_brute_force_line(line) for line in text.split("\n"))


def vigenere_encrypt(text: str, key: str) -> str:
    if not key or not key.isalpha():
        raise ValueError("Key must be non-empty and contain only letters")
    key = key.upper()
    result = []
    ki = 0
    for ch in text:
        if ch.isalpha():
            shift = ord(key[ki % len(key)]) - ord("A")
            base = ord("A") if ch.isupper() else ord("a")
            result.append(chr((ord(ch) - base + shift) % 26 + base))
            ki += 1
        else:
            result.append(ch)
    return "".join(result)


def vigenere_decrypt(text: str, key: str) -> str:
    if not key or not key.isalpha():
        raise ValueError("Key must be non-empty and contain only letters")
    key = key.upper()
    result = []
    ki = 0
    for ch in text:
        if ch.isalpha():
            shift = ord(key[ki % len(key)]) - ord("A")
            base = ord("A") if ch.isupper() else ord("a")
            result.append(chr((ord(ch) - base - shift) % 26 + base))
            ki += 1
        else:
            result.append(ch)
    return "".join(result)


def _rail_fence_encrypt_line(text: str, rails: int = 3) -> str:
    if rails < 2:
        raise ValueError("Rails must be at least 2")
    fence = [[] for _ in range(rails)]
    rail, direction = 0, 1
    for ch in text:
        fence[rail].append(ch)
        if rail == 0:
            direction = 1
        elif rail == rails - 1:
            direction = -1
        rail += direction
    return "".join("".join(row) for row in fence)


def rail_fence_encrypt(text: str, rails: int = 3) -> str:
    if "\n" not in text:
        return _rail_fence_encrypt_line(text, rails)
    return "\n".join(_rail_fence_encrypt_line(line, rails) for line in text.split("\n"))


def _rail_fence_decrypt_line(text: str, rails: int = 3) -> str:
    if rails < 2:
        raise ValueError("Rails must be at least 2")
    n = len(text)
    pattern = []
    rail, direction = 0, 1
    for _i in range(n):
        pattern.append(rail)
        if rail == 0:
            direction = 1
        elif rail == rails - 1:
            direction = -1
        rail += direction
    sorted_indices = sorted(range(n), key=lambda i: pattern[i])
    result = [""] * n
    for idx, char in zip(sorted_indices, text, strict=False):
        result[idx] = char
    return "".join(result)


def rail_fence_decrypt(text: str, rails: int = 3) -> str:
    if "\n" not in text:
        return _rail_fence_decrypt_line(text, rails)
    return "\n".join(_rail_fence_decrypt_line(line, rails) for line in text.split("\n"))


def _playfair_encrypt_line(text: str, key: str) -> str:
    if not key:
        raise ValueError("Key must be non-empty")
    key = key.upper().replace("J", "I")
    seen = set()
    matrix = []
    for ch in key + "ABCDEFGHIKLMNOPQRSTUVWXYZ":
        if ch.isalpha() and ch not in seen:
            seen.add(ch)
            matrix.append(ch)
    # Prepare text: uppercase, replace J with I, split into digrams
    cleaned = re.sub(r"[^A-Za-z]", "", text).upper().replace("J", "I")
    pairs = []
    i = 0
    while i < len(cleaned):
        a = cleaned[i]
        b = cleaned[i + 1] if i + 1 < len(cleaned) else "X"
        if a == b:
            b = "X"
            i += 1
        else:
            i += 2
        pairs.append((a, b))

    # Encrypt pairs
    def pos(c):
        idx = matrix.index(c)
        return idx // 5, idx % 5

    result = []
    for a, b in pairs:
        r1, c1 = pos(a)
        r2, c2 = pos(b)
        if r1 == r2:
            result.append(matrix[r1 * 5 + (c1 + 1) % 5])
            result.append(matrix[r2 * 5 + (c2 + 1) % 5])
        elif c1 == c2:
            result.append(matrix[((r1 + 1) % 5) * 5 + c1])
            result.append(matrix[((r2 + 1) % 5) * 5 + c2])
        else:
            result.append(matrix[r1 * 5 + c2])
            result.append(matrix[r2 * 5 + c1])
    return "".join(result)


def playfair_encrypt(text: str, key: str) -> str:
    if "\n" not in text:
        return _playfair_encrypt_line(text, key)
    return "\n".join(_playfair_encrypt_line(line, key) for line in text.split("\n"))


def substitution_cipher(text: str, mapping: str) -> str:
    if len(mapping) != 26:
        raise ValueError("Mapping must be exactly 26 characters (A-Z substitution)")
    mapping = mapping.upper()
    result = []
    for ch in text:
        if "a" <= ch <= "z":
            result.append(mapping[ord(ch) - ord("a")].lower())
        elif "A" <= ch <= "Z":
            result.append(mapping[ord(ch) - ord("A")])
        else:
            result.append(ch)
    return "".join(result)


def _columnar_transposition_line(text: str, key: str) -> str:
    if not key:
        raise ValueError("Key must be non-empty")
    key = key.upper()
    num_cols = len(key)
    # Pad text to fill grid
    padded = text + " " * ((num_cols - len(text) % num_cols) % num_cols)
    # Create grid
    rows = [padded[i : i + num_cols] for i in range(0, len(padded), num_cols)]
    # Get column order from key
    order = sorted(range(num_cols), key=lambda i: key[i])
    # Read columns in key order
    result = []
    for col in order:
        for row in rows:
            result.append(row[col])
    return "".join(result)


def columnar_transposition(text: str, key: str) -> str:
    if "\n" not in text:
        return _columnar_transposition_line(text, key)
    return "\n".join(
        _columnar_transposition_line(line, key) for line in text.split("\n")
    )


def _nato_phonetic_line(text: str) -> str:
    NATO = {
        "A": "Alpha",
        "B": "Bravo",
        "C": "Charlie",
        "D": "Delta",
        "E": "Echo",
        "F": "Foxtrot",
        "G": "Golf",
        "H": "Hotel",
        "I": "India",
        "J": "Juliet",
        "K": "Kilo",
        "L": "Lima",
        "M": "Mike",
        "N": "November",
        "O": "Oscar",
        "P": "Papa",
        "Q": "Quebec",
        "R": "Romeo",
        "S": "Sierra",
        "T": "Tango",
        "U": "Uniform",
        "V": "Victor",
        "W": "Whiskey",
        "X": "X-ray",
        "Y": "Yankee",
        "Z": "Zulu",
        "0": "Zero",
        "1": "One",
        "2": "Two",
        "3": "Three",
        "4": "Four",
        "5": "Five",
        "6": "Six",
        "7": "Seven",
        "8": "Eight",
        "9": "Niner",
    }
    # Check if input is NATO phonetic (reverse conversion)
    words = text.strip().split()
    reverse_nato = {v.upper(): k for k, v in NATO.items()}
    if all(w.upper() in reverse_nato for w in words):
        return "".join(reverse_nato[w.upper()] for w in words)
    # Forward conversion
    result = []
    for ch in text.upper():
        if ch in NATO:
            result.append(NATO[ch])
        elif ch == " ":
            result.append("[space]")
        else:
            result.append(ch)
    return " ".join(result)


def nato_phonetic(text: str) -> str:
    if "\n" not in text:
        return _nato_phonetic_line(text)
    return "\n".join(_nato_phonetic_line(line) for line in text.split("\n"))


def _bacon_cipher_line(text: str) -> str:
    BACON = {
        "A": "AAAAA",
        "B": "AAAAB",
        "C": "AAABA",
        "D": "AAABB",
        "E": "AABAA",
        "F": "AABAB",
        "G": "AABBA",
        "H": "AABBB",
        "I": "ABAAA",
        "J": "ABAAA",
        "K": "ABAAB",
        "L": "ABABA",
        "M": "ABABB",
        "N": "ABBAA",
        "O": "ABBAB",
        "P": "ABBBA",
        "Q": "ABBBB",
        "R": "BAAAA",
        "S": "BAAAB",
        "T": "BAABA",
        "U": "BAABB",
        "V": "BAABB",
        "W": "BABAA",
        "X": "BABAB",
        "Y": "BABBA",
        "Z": "BABBB",
    }
    # Auto-detect: treat input as ciphertext only when the cleaned text is
    # *exclusively* A/B and its length is a positive multiple of 5 (a Bacon
    # codeword is always 5 letters). Without the length check, any plaintext
    # that happens to use only A/B (e.g. "AB", "BABA", "abba") is mistakenly
    # routed through the decoder and returns garbage / an empty string.
    cleaned = text.strip().replace(" ", "")
    is_ciphertext = (
        len(cleaned) >= 5
        and len(cleaned) % 5 == 0
        and all(c in "AaBb" for c in cleaned)
    )
    if is_ciphertext:
        REVERSE = {v: k for k, v in BACON.items()}
        upper = cleaned.upper()
        result = []
        for i in range(0, len(upper), 5):
            chunk = upper[i : i + 5]
            if chunk in REVERSE:
                result.append(REVERSE[chunk])
        return "".join(result)
    # Forward encoding
    result = []
    for ch in text.upper():
        if ch in BACON:
            result.append(BACON[ch])
        elif ch == " ":
            result.append(" ")
    return " ".join(result) if " " not in "".join(result) else "".join(result)


def bacon_cipher(text: str) -> str:
    if "\n" not in text:
        return _bacon_cipher_line(text)
    return "\n".join(_bacon_cipher_line(line) for line in text.split("\n"))


# ── Encoding Extensions (new) ──────────────────────────────────────────


def _base32_decode_line(text: str) -> str:
    padded = text.strip()
    padded += "=" * ((8 - len(padded) % 8) % 8)
    return base64.b32decode(padded).decode("utf-8")


base32_encode = _per_line(lambda s: base64.b32encode(s.encode("utf-8")).decode("ascii"))
base32_decode = _per_line(_base32_decode_line)

ascii85_encode = _per_line(
    lambda s: base64.a85encode(s.encode("utf-8")).decode("ascii")
)
ascii85_decode = _per_line(lambda s: base64.a85decode(s.strip()).decode("utf-8"))


# ── Developer Tool Functions (new) ─────────────────────────────────────


def xml_to_json(text: str) -> str:
    """Convert an XML document to JSON using stdlib ElementTree.

    Mirrors xmltodict's structure: a single-key dict with the root tag, where
    each element becomes a dict of its children (or a string if it's a leaf
    with text). Repeated child tags become a list. Attributes are stored
    under ``@name`` keys; element text under ``#text`` when attributes/children
    are also present.
    """
    import xml.etree.ElementTree as ET

    def node_to_obj(elem):
        children = list(elem)
        attrs = {f"@{k}": v for k, v in elem.attrib.items()}
        text = (elem.text or "").strip()

        if not children and not attrs:
            return text or None
        if not children:
            return {**attrs, "#text": text} if text else attrs

        # Group children by tag — repeated tags collapse to a list.
        grouped: dict = {}
        for child in children:
            value = node_to_obj(child)
            if child.tag in grouped:
                if not isinstance(grouped[child.tag], list):
                    grouped[child.tag] = [grouped[child.tag]]
                grouped[child.tag].append(value)
            else:
                grouped[child.tag] = value

        result = {**attrs, **grouped}
        if text:
            result["#text"] = text
        return result

    stripped = text.strip()
    try:
        root = ET.fromstring(stripped)
        return json.dumps({root.tag: node_to_obj(root)}, indent=2, ensure_ascii=False)
    except ET.ParseError:
        # XML requires a single root, but users often paste several sibling
        # documents in one go. Wrap them in a synthetic root, parse, then
        # emit each top-level child as its own JSON object separated by a
        # blank line — preserving the "one document per input" mental model
        # rather than merging them into a single combined object.
        try:
            wrapper = ET.fromstring(f"<root>{stripped}</root>")
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}") from e
        return "\n\n".join(
            json.dumps({child.tag: node_to_obj(child)}, indent=2, ensure_ascii=False)
            for child in wrapper
        )


def csv_to_table(text: str) -> str:
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return text
    # Calculate column widths
    widths = [0] * len(rows[0])
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell.strip()))
    # Build markdown table
    lines = []
    # Header
    header = (
        "| "
        + " | ".join(cell.strip().ljust(widths[i]) for i, cell in enumerate(rows[0]))
        + " |"
    )
    lines.append(header)
    # Separator
    sep = "| " + " | ".join("-" * widths[i] for i in range(len(rows[0]))) + " |"
    lines.append(sep)
    # Data rows
    for row in rows[1:]:
        data = (
            "| "
            + " | ".join(
                (row[i].strip() if i < len(row) else "").ljust(widths[i])
                for i in range(len(rows[0]))
            )
            + " |"
        )
        lines.append(data)
    return "\n".join(lines)


def sql_insert_gen(text: str) -> str:
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        raise ValueError("Input must have a header row and at least one data row")
    headers = [h.strip() for h in rows[0]]
    table_name = "table_name"
    lines = []
    for row in rows[1:]:
        values = []
        for cell in row:
            cell = cell.strip()
            try:
                float(cell)
                values.append(cell)
            except ValueError:
                values.append(f"'{cell.replace(chr(39), chr(39) * 2)}'")
        lines.append(
            f"INSERT INTO {table_name} ({', '.join(headers)}) VALUES ({', '.join(values)});"
        )  # noqa: S608
    return "\n".join(lines)
