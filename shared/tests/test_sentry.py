"""Tests for Sentry init + the PII scrubber (_before_send)."""

import sys
import types
from unittest.mock import MagicMock

import pytest

from fixmytext_shared.config.base import BaseSharedSettings
from fixmytext_shared.observability import sentry as sentry_mod
from fixmytext_shared.observability.sentry import _before_send, init_sentry


def _settings(**overrides) -> BaseSharedSettings:
    """Settings with env-file loading disabled.

    Without _env_file=None a local backend/.env leaks SENTRY_* values into
    fields the test leaves unset (CI has no .env, so it never noticed).
    """
    return BaseSharedSettings(_env_file=None, **overrides)


def _event(request: dict | None = None, extra: dict | None = None) -> dict:
    event: dict = {}
    if request is not None:
        event["request"] = request
    if extra is not None:
        event["extra"] = extra
    return event


class TestBeforeSend:
    def test_scrubs_pii_body_fields(self):
        event = _event(
            request={
                "data": {"text": "user text", "password": "hunter2", "plan": "pro"}
            }
        )
        result = _before_send(event, {})
        assert result["request"]["data"] == {
            "text": "[Filtered]",
            "password": "[Filtered]",
            "plan": "pro",
        }

    def test_body_scrub_is_case_insensitive(self):
        event = _event(request={"data": {"Token": "abc", "REFRESH_TOKEN": "def"}})
        data = _before_send(event, {})["request"]["data"]
        assert data == {"Token": "[Filtered]", "REFRESH_TOKEN": "[Filtered]"}

    def test_non_dict_body_left_alone(self):
        event = _event(request={"data": "raw-body"})
        assert _before_send(event, {})["request"]["data"] == "raw-body"

    def test_scrubs_sensitive_headers_only(self):
        event = _event(
            request={
                "headers": {
                    "Authorization": "Bearer x",
                    "Cookie": "sid=1",
                    "X-Request-ID": "id-1",
                }
            }
        )
        headers = _before_send(event, {})["request"]["headers"]
        assert headers["Authorization"] == "[Filtered]"
        assert headers["Cookie"] == "[Filtered]"
        assert headers["X-Request-ID"] == "id-1"

    def test_clears_cookies(self):
        event = _event(request={"cookies": {"session": "abc"}})
        assert _before_send(event, {})["request"]["cookies"] == {}

    def test_scrubs_extra_context_on_substring_match(self):
        event = _event(extra={"request_token_digest": "abc", "attempt": 3})
        extra = _before_send(event, {})["extra"]
        assert extra["request_token_digest"] == "[Filtered]"
        assert extra["attempt"] == 3

    def test_event_without_request_passes_through(self):
        result = _before_send({"message": "boom"}, {})
        assert result["message"] == "boom"


class TestInitSentry:
    @pytest.fixture
    def fake_init(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(sentry_mod.sentry_sdk, "init", fake)
        return fake

    def test_noop_without_dsn(self, fake_init):
        init_sentry(_settings(SENTRY_DSN=""))
        fake_init.assert_not_called()

    def test_initialises_with_scrubber_and_settings(self, fake_init):
        settings = _settings(
            SENTRY_DSN="https://key@o0.ingest.sentry.io/1",
            ENVIRONMENT="staging",
            SENTRY_TRACES_SAMPLE_RATE=0.25,
        )
        init_sentry(settings)
        fake_init.assert_called_once()
        kwargs = fake_init.call_args.kwargs
        assert kwargs["dsn"] == "https://key@o0.ingest.sentry.io/1"
        assert kwargs["environment"] == "staging"  # falls back to ENVIRONMENT
        assert kwargs["release"] is None  # empty SENTRY_RELEASE -> None
        assert kwargs["before_send"] is _before_send
        assert kwargs["send_default_pii"] is False
        assert kwargs["include_local_variables"] is False
        assert kwargs["traces_sample_rate"] == 0.25
        names = {type(i).__name__ for i in kwargs["integrations"]}
        assert {"FastApiIntegration", "HttpxIntegration"} <= names

    def test_sentry_environment_and_release_override(self, fake_init):
        settings = _settings(
            SENTRY_DSN="https://key@o0.ingest.sentry.io/1",
            ENVIRONMENT="production",
            SENTRY_ENVIRONMENT="canary",
            SENTRY_RELEASE="1.2.3+abc",
        )
        init_sentry(settings)
        kwargs = fake_init.call_args.kwargs
        assert kwargs["environment"] == "canary"
        assert kwargs["release"] == "1.2.3+abc"

    def test_asyncpg_integration_skipped_when_driver_missing(
        self, fake_init, monkeypatch
    ):
        # A None sys.modules entry makes the import raise ImportError,
        # mimicking an environment without asyncpg (text-svc, ai-svc, CI).
        monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.asyncpg", None)
        init_sentry(_settings(SENTRY_DSN="https://key@o0.ingest.sentry.io/1"))
        names = {type(i).__name__ for i in fake_init.call_args.kwargs["integrations"]}
        assert names == {"FastApiIntegration", "HttpxIntegration"}

    def test_asyncpg_integration_included_when_available(self, fake_init, monkeypatch):
        fake_module = types.ModuleType("sentry_sdk.integrations.asyncpg")
        fake_module.AsyncPGIntegration = type("AsyncPGIntegration", (), {})
        monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.asyncpg", fake_module)
        init_sentry(_settings(SENTRY_DSN="https://key@o0.ingest.sentry.io/1"))
        names = {type(i).__name__ for i in fake_init.call_args.kwargs["integrations"]}
        assert "AsyncPGIntegration" in names
