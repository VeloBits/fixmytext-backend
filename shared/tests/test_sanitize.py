"""Tests for sanitize + PII redaction filters."""

import logging

from fixmytext_shared.observability.sanitize import (
    LogSanitizationFilter,
    PiiRedactionFilter,
    sanitize_log_value,
)


def _make_record(msg: str, args=()) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=msg,
        args=args,
        exc_info=None,
    )


class TestSanitizeLogValue:
    def test_strips_newlines(self):
        assert sanitize_log_value("hello\nworld") == "hello world"

    def test_strips_carriage_returns(self):
        assert sanitize_log_value("hello\rworld") == "hello world"

    def test_strips_null_bytes(self):
        assert sanitize_log_value("hello\x00world") == "hello world"

    def test_preserves_tabs(self):
        # Tab (\x09) is NOT in the regex range — it's allowed.
        assert sanitize_log_value("hello\tworld") == "hello\tworld"

    def test_coerces_non_str(self):
        assert sanitize_log_value(42) == "42"


class TestLogSanitizationFilter:
    def test_strips_control_chars_from_msg(self):
        f = LogSanitizationFilter()
        record = _make_record("user said: hello\nattack: hi")
        f.filter(record)
        assert "\n" not in record.msg

    def test_strips_control_chars_from_tuple_args(self):
        f = LogSanitizationFilter()
        record = _make_record("user: %s", ("evil\nlog",))
        f.filter(record)
        assert "\n" not in record.args[0]

    def test_strips_control_chars_from_dict_args(self):
        # LogRecord with a dict for args has a Python-internal quirk
        # (it tries args[0] for mapping-style logging). We construct the
        # record directly and bypass __init__ for the dict-args case so
        # the test isolates the filter's behaviour.
        f = LogSanitizationFilter()
        record = _make_record("user: %(name)s")
        record.args = {"name": "evil\nuser"}
        f.filter(record)
        assert "\n" not in record.args["name"]


class TestPiiRedactionFilter:
    def test_redacts_text_keyword(self):
        f = PiiRedactionFilter()
        record = _make_record("User submitted text: hello world")
        f.filter(record)
        assert record.msg == "[REDACTED]"

    def test_redacts_password_keyword(self):
        f = PiiRedactionFilter()
        record = _make_record("password reset requested")
        f.filter(record)
        assert record.msg == "[REDACTED]"

    def test_redacts_token_keyword(self):
        f = PiiRedactionFilter()
        record = _make_record("refreshing token")
        f.filter(record)
        assert record.msg == "[REDACTED]"

    def test_does_not_redact_safe_message(self):
        f = PiiRedactionFilter()
        record = _make_record("User logged in successfully")
        f.filter(record)
        assert record.msg == "User logged in successfully"

    def test_clears_args_when_redacting(self):
        f = PiiRedactionFilter()
        record = _make_record("text value: %s", ("some content",))
        f.filter(record)
        assert record.msg == "[REDACTED]"
        assert record.args == ()
