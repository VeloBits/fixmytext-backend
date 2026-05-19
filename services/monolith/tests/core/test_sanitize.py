"""Tests for app/core/sanitize.py — sanitize_log_value and LogSanitizationFilter."""

import logging

from app.core.sanitize import LogSanitizationFilter, sanitize_log_value

# ── sanitize_log_value ─────────────────────────────────────────────────────


class TestSanitizeLogValue:
    def test_plain_string_unchanged(self):
        assert sanitize_log_value("hello world") == "hello world"

    def test_strips_newline(self):
        assert sanitize_log_value("line1\nline2") == "line1 line2"

    def test_strips_carriage_return(self):
        assert sanitize_log_value("line1\rline2") == "line1 line2"

    def test_strips_crlf(self):
        assert sanitize_log_value("line1\r\nline2") == "line1  line2"

    def test_strips_null_byte(self):
        assert sanitize_log_value("before\x00after") == "before after"

    def test_strips_other_control_chars(self):
        # \x01 (SOH), \x08 (BS), \x1f (US), \x7f (DEL)
        result = sanitize_log_value("a\x01b\x08c\x1fd\x7fe")
        assert result == "a b c d e"

    def test_preserves_tab(self):
        # Tab (\x09) is intentionally allowed
        assert sanitize_log_value("col1\tcol2") == "col1\tcol2"

    def test_converts_non_string_to_str(self):
        assert sanitize_log_value(42) == "42"
        assert sanitize_log_value(None) == "None"

    def test_non_string_with_newline_in_repr(self):
        class Sneaky:
            def __str__(self):
                return "evil\ninjection"

        assert sanitize_log_value(Sneaky()) == "evil injection"

    def test_empty_string(self):
        assert sanitize_log_value("") == ""

    def test_log_injection_attack_vector(self):
        """Simulates a classic log injection: fake a new log line."""
        attack = "normal\n2026-04-13 INFO [fake] Forged log entry"
        result = sanitize_log_value(attack)
        assert "\n" not in result
        assert "Forged" in result  # content preserved, just on same line


# ── LogSanitizationFilter ──────────────────────────────────────────────────


class TestLogSanitizationFilter:
    def _make_record(self, msg, args=None):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=args,
            exc_info=None,
        )
        return record

    def test_sanitizes_msg_newlines(self):
        filt = LogSanitizationFilter()
        record = self._make_record("line1\nline2\rline3")
        filt.filter(record)
        assert "\n" not in record.msg
        assert "\r" not in record.msg

    def test_sanitizes_tuple_args(self):
        filt = LogSanitizationFilter()
        record = self._make_record("event=%s id=%s", ("evil\nvalue", "clean"))
        filt.filter(record)
        assert record.args[0] == "evil value"
        assert record.args[1] == "clean"

    def test_sanitizes_dict_args(self):
        filt = LogSanitizationFilter()
        record = self._make_record(
            "%(name)s %(value)s", {"name": "ok", "value": "bad\nstuff"}
        )
        filt.filter(record)
        assert record.args["value"] == "bad stuff"
        assert record.args["name"] == "ok"

    def test_preserves_non_string_args(self):
        filt = LogSanitizationFilter()
        record = self._make_record("count=%s", (42,))
        filt.filter(record)
        assert record.args == (42,)

    def test_always_returns_true(self):
        filt = LogSanitizationFilter()
        record = self._make_record("test")
        assert filt.filter(record) is True

    def test_handles_none_args(self):
        filt = LogSanitizationFilter()
        record = self._make_record("no args")
        record.args = None
        filt.filter(record)
        assert record.args is None

    def test_handles_non_string_msg(self):
        filt = LogSanitizationFilter()
        record = self._make_record("test")
        record.msg = 12345  # non-string msg
        filt.filter(record)
        assert record.msg == 12345  # left as-is

    def test_integration_with_logger(self, caplog):
        """Verify filter works end-to-end with Python logging."""
        test_logger = logging.getLogger("test_sanitize_integration")
        handler = logging.StreamHandler()
        handler.addFilter(LogSanitizationFilter())
        test_logger.addHandler(handler)
        test_logger.propagate = False

        with caplog.at_level(logging.INFO, logger="test_sanitize_integration"):
            test_logger.info("user=%s", "attacker\nINFO [fake] pwned")

        test_logger.removeHandler(handler)
