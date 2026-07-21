"""Tests for OTel logs bootstrap (init/shutdown + sanitizer attachment)."""

import logging
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk._logs.export import LogExporter, LogExportResult

from fixmytext_shared.config.base import BaseSharedSettings
from fixmytext_shared.observability import logs as logs_mod
from fixmytext_shared.observability.sanitize import (
    LogSanitizationFilter,
    PiiRedactionFilter,
)


class _FakeExporter(LogExporter):
    """Stand-in for OTLPLogExporter — records kwargs, never hits the network."""

    instances: list["_FakeExporter"] = []

    def __init__(self, *, endpoint: str, headers: dict):
        self.endpoint = endpoint
        self.headers = headers
        _FakeExporter.instances.append(self)

    def export(self, batch):
        return LogExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True

    def shutdown(self):
        return None


@pytest.fixture(autouse=True)
def _isolated_otel(monkeypatch):
    """Swap in a fake exporter/provider-setter and restore logging state."""
    monkeypatch.setattr(logs_mod, "OTLPLogExporter", _FakeExporter)
    monkeypatch.setattr(logs_mod, "set_logger_provider", MagicMock())
    _FakeExporter.instances.clear()
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    yield
    logs_mod.shutdown_logs_otel()
    for handler in list(root.handlers):
        if handler not in handlers_before:
            root.removeHandler(handler)


def _settings(**overrides) -> BaseSharedSettings:
    return BaseSharedSettings(**overrides)


class TestAttachLogSanitizers:
    def test_attaches_both_filters(self):
        handler = logging.NullHandler()
        logs_mod.attach_log_sanitizers(handler)
        filter_types = [type(f) for f in handler.filters]
        assert LogSanitizationFilter in filter_types
        assert PiiRedactionFilter in filter_types


class TestInitLogsOtel:
    def test_noop_without_endpoint(self):
        handlers_before = list(logging.getLogger().handlers)
        logs_mod.init_logs_otel(_settings(OTEL_EXPORTER_OTLP_ENDPOINT=""))
        assert _FakeExporter.instances == []
        assert logs_mod._logger_provider is None
        assert logs_mod.set_logger_provider.call_count == 0
        assert list(logging.getLogger().handlers) == handlers_before

    def test_init_wires_exporter_provider_and_root_handler(self):
        root = logging.getLogger()
        handler_ids_before = {id(h) for h in root.handlers}
        logs_mod.init_logs_otel(
            _settings(
                OTEL_EXPORTER_OTLP_ENDPOINT="http://loki:3100/otlp/",
                OTEL_EXPORTER_OTLP_HEADERS=(
                    "Authorization=Basic%20dXNlcg==,X-Scope-OrgID= demo ,malformed"
                ),
                OTEL_SERVICE_NAME="test-svc",
                VERSION="1.2.3",
                ENVIRONMENT="test",
            )
        )
        # Exporter got the normalised endpoint and the parsed/unquoted headers;
        # the header fragment without "=" was skipped.
        assert len(_FakeExporter.instances) == 1
        exporter = _FakeExporter.instances[0]
        assert exporter.endpoint == "http://loki:3100/otlp/v1/logs"
        assert exporter.headers == {
            "Authorization": "Basic dXNlcg==",
            "X-Scope-OrgID": "demo",
        }
        # A single OTLP handler was added to the root logger, with both
        # sanitisation filters attached (M-9).
        added = [h for h in root.handlers if id(h) not in handler_ids_before]
        assert len(added) == 1
        filter_types = {type(f) for f in added[0].filters}
        assert {LogSanitizationFilter, PiiRedactionFilter} <= filter_types
        # The provider was registered globally and kept for shutdown.
        assert logs_mod._logger_provider is not None
        logs_mod.set_logger_provider.assert_called_once_with(logs_mod._logger_provider)


class TestShutdownLogsOtel:
    def test_shutdown_is_idempotent(self):
        logs_mod.init_logs_otel(
            _settings(OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4318")
        )
        assert logs_mod._logger_provider is not None
        logs_mod.shutdown_logs_otel()
        assert logs_mod._logger_provider is None
        logs_mod.shutdown_logs_otel()  # second call must be a no-op
        assert logs_mod._logger_provider is None
