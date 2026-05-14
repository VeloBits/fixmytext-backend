"""Tests for Sentry and OTel observability modules."""

import logging
from unittest.mock import patch

from app.core.observability_logs import PiiRedactionFilter


class TestPiiRedactionFilter:
    def _make_record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_redacts_text_keyword_in_message(self) -> None:
        f = PiiRedactionFilter()
        record = self._make_record("User submitted text: hello world")
        f.filter(record)
        assert record.msg == "[REDACTED]"

    def test_redacts_password_keyword(self) -> None:
        f = PiiRedactionFilter()
        record = self._make_record("password reset requested")
        f.filter(record)
        assert record.msg == "[REDACTED]"

    def test_does_not_redact_safe_message(self) -> None:
        f = PiiRedactionFilter()
        record = self._make_record("User logged in successfully")
        f.filter(record)
        assert record.msg == "User logged in successfully"

    def test_clears_args_when_redacting(self) -> None:
        f = PiiRedactionFilter()
        record = self._make_record("text value: %s")
        record.args = ("some content",)
        f.filter(record)
        assert record.msg == "[REDACTED]"
        assert record.args == ()


class TestSentryBeforeSend:
    def test_strips_text_from_request_data(self) -> None:
        from app.core.sentry import _before_send

        event = {"request": {"data": {"text": "user content", "action": "submit"}}}
        result = _before_send(event, {})
        assert result["request"]["data"]["text"] == "[Filtered]"
        assert result["request"]["data"]["action"] == "submit"

    def test_strips_password_from_request_data(self) -> None:
        from app.core.sentry import _before_send

        event = {"request": {"data": {"password": "secret"}}}
        result = _before_send(event, {})
        assert result["request"]["data"]["password"] == "[Filtered]"

    def test_strips_authorization_header(self) -> None:
        from app.core.sentry import _before_send

        event = {
            "request": {
                "headers": {
                    "authorization": "Bearer token123",
                    "content-type": "application/json",
                }
            }
        }
        result = _before_send(event, {})
        assert result["request"]["headers"]["authorization"] == "[Filtered]"
        assert result["request"]["headers"]["content-type"] == "application/json"

    def test_clears_cookies(self) -> None:
        from app.core.sentry import _before_send

        event = {"request": {"cookies": {"session": "abc"}}}
        result = _before_send(event, {})
        assert result["request"]["cookies"] == {}

    def test_safe_event_passes_through(self) -> None:
        from app.core.sentry import _before_send

        event = {"request": {"data": {"action": "click", "page": "home"}}}
        result = _before_send(event, {})
        assert result["request"]["data"]["action"] == "click"


class TestInitSentryNoOp:
    def test_no_op_when_dsn_empty(self) -> None:
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.SENTRY_DSN = ""
            import sentry_sdk

            with patch.object(sentry_sdk, "init") as mock_init:
                from app.core.sentry import init_sentry

                init_sentry()
                mock_init.assert_not_called()


class TestInitLogsOtelNoOp:
    def test_no_op_when_endpoint_empty(self) -> None:
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.OTEL_EXPORTER_OTLP_ENDPOINT = ""
            from app.core.observability_logs import init_logs_otel

            # Should not raise, should be a no-op
            init_logs_otel()
