"""Tests for the region detection service.

Covers the in-process TTL cache added to stay under ip-api.com's free-tier
rate limit (45 req/min). At 1k-10k users every uncached catalog request with
no explicit region param would make an outbound HTTP call, saturating the
limit immediately (H-1).
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Cache correctness ─────────────────────────────────────────────────────────


def test_cache_set_and_get_within_ttl():
    """A freshly written entry must be returned within its TTL."""
    from app.services import region_service

    region_service._REGION_CACHE.clear()
    region_service._cache_set("10.0.0.1", "GB")
    assert region_service._cache_get("10.0.0.1") == "GB"
    region_service._REGION_CACHE.clear()


def test_cache_get_returns_none_for_expired_entry():
    """An entry whose expiry timestamp is in the past must not be returned."""
    from app.services import region_service

    region_service._REGION_CACHE.clear()
    region_service._REGION_CACHE["5.5.5.5"] = ("IN", time.monotonic() - 1)
    assert region_service._cache_get("5.5.5.5") is None
    region_service._REGION_CACHE.clear()


def test_cache_get_returns_none_for_unknown_ip():
    from app.services import region_service

    region_service._REGION_CACHE.clear()
    assert region_service._cache_get("0.0.0.0") is None


# ── detect_region: HTTP call suppression ─────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_region_only_calls_http_once_per_ip():
    """The second call for the same IP must return the cached region without
    making another outbound HTTP request (H-1 — rate-limit protection)."""
    from app.services import region_service

    region_service._REGION_CACHE.clear()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"countryCode": "IN"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.services.region_service.httpx.AsyncClient", return_value=mock_client):
        r1 = await region_service.detect_region("203.0.113.1")
        r2 = await region_service.detect_region("203.0.113.1")

    assert r1 == "IN"
    assert r2 == "IN"
    assert mock_client.get.call_count == 1, (
        "Expected exactly 1 HTTP call; cache must serve the second request"
    )
    region_service._REGION_CACHE.clear()


@pytest.mark.asyncio
async def test_detect_region_calls_http_for_each_distinct_ip():
    """Different IPs must each trigger their own HTTP lookup."""
    from app.services import region_service

    region_service._REGION_CACHE.clear()

    responses = [
        MagicMock(**{"status_code": 200, "json.return_value": {"countryCode": "US"}}),
        MagicMock(**{"status_code": 200, "json.return_value": {"countryCode": "IN"}}),
    ]

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=responses)

    with patch("app.services.region_service.httpx.AsyncClient", return_value=mock_client):
        r1 = await region_service.detect_region("1.1.1.1")
        r2 = await region_service.detect_region("8.8.8.8")

    assert r1 == "US"
    assert r2 == "IN"
    assert mock_client.get.call_count == 2
    region_service._REGION_CACHE.clear()


@pytest.mark.asyncio
async def test_detect_region_returns_default_on_http_failure():
    """When the HTTP call fails, detect_region must return the default region
    without raising (callers fall back gracefully)."""
    from app.services import region_service

    region_service._REGION_CACHE.clear()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("network error"))

    with patch("app.services.region_service.httpx.AsyncClient", return_value=mock_client):
        result = await region_service.detect_region("1.2.3.4")

    assert result == region_service.DEFAULT_REGION
    region_service._REGION_CACHE.clear()


@pytest.mark.asyncio
async def test_detect_region_caches_local_ip_under_sentinel_key():
    """Local/private IPs are resolved via the server's public IP and cached
    under '__local__' so multiple local callers share one cached lookup."""
    from app.services import region_service

    region_service._REGION_CACHE.clear()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"countryCode": "IN"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.services.region_service.httpx.AsyncClient", return_value=mock_client):
        await region_service.detect_region("127.0.0.1")
        await region_service.detect_region("localhost")

    # Both local-IP requests share the '__local__' cache key
    assert mock_client.get.call_count == 1
    assert "__local__" in region_service._REGION_CACHE
    region_service._REGION_CACHE.clear()
