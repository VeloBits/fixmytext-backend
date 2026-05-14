import sentry_sdk
from sentry_sdk.integrations.asyncpg import AsyncPGIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration

from app.core.config import settings

_PII_KEYS = frozenset(
    {
        "text",
        "prompt",
        "input",
        "content",
        "password",
        "refresh_token",
        "token",
        "razorpay_signature",
    }
)
_PII_HEADERS = frozenset({"authorization", "cookie"})


def _before_send(event: dict, hint: dict) -> dict:  # type: ignore[type-arg]
    request = event.get("request", {})

    # Scrub request body fields
    data = request.get("data")
    if isinstance(data, dict):
        request["data"] = {
            k: "[Filtered]" if k.lower() in _PII_KEYS else v for k, v in data.items()
        }

    # Scrub sensitive headers
    headers = request.get("headers", {})
    if isinstance(headers, dict):
        request["headers"] = {
            k: "[Filtered]" if k.lower() in _PII_HEADERS else v
            for k, v in headers.items()
        }

    # Clear cookies
    if "cookies" in request:
        request["cookies"] = {}

    # Scrub extra context
    extra = event.get("extra", {})
    if isinstance(extra, dict):
        event["extra"] = {
            k: "[Filtered]"
            if any(p in k.lower() for p in _PII_KEYS | _PII_HEADERS)
            else v
            for k, v in extra.items()
        }

    return event


def init_sentry() -> None:
    dsn = settings.SENTRY_DSN
    if not dsn:
        return

    environment = settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=settings.SENTRY_RELEASE or None,
        integrations=[
            FastApiIntegration(),
            AsyncPGIntegration(),
            HttpxIntegration(),
        ],
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
        include_local_variables=False,
        before_send=_before_send,
    )
