import logging

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from app.core.config import settings
from app.core.sanitize import LogSanitizationFilter

_PII_PATTERN_KEYS = frozenset(
    {
        "text",
        "prompt",
        "password",
        "token",
        "cookie",
        "authorization",
    }
)

_logger_provider: LoggerProvider | None = None


class PiiRedactionFilter(logging.Filter):
    """Redacts PII key patterns from log record message and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for key in _PII_PATTERN_KEYS:
                if key in record.msg.lower():
                    record.msg = "[REDACTED]"
                    record.args = ()
                    return True
        return True


def init_logs_otel() -> None:
    global _logger_provider

    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if not endpoint:
        return

    headers: dict[str, str] = {}
    raw_headers = settings.OTEL_EXPORTER_OTLP_HEADERS
    if raw_headers:
        for part in raw_headers.split(","):
            if "=" in part:
                k, _, v = part.partition("=")
                headers[k.strip()] = v.strip()

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.VERSION,
            "deployment.environment": settings.ENVIRONMENT,
        }
    )

    provider = LoggerProvider(resource=resource)
    exporter = OTLPLogExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/logs",
        headers=headers,
    )
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    handler.addFilter(LogSanitizationFilter())
    handler.addFilter(PiiRedactionFilter())
    logging.getLogger().addHandler(handler)

    _logger_provider = provider


def shutdown_logs_otel(timeout_millis: int = 5000) -> None:
    if _logger_provider is not None:
        _logger_provider.shutdown()
