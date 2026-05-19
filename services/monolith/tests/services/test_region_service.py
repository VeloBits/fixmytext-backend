"""Tests for app/services/region_service.py"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.conftest import make_user

# ── region_service ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_region_india():
    from app.services.region_service import detect_region

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"countryCode": "IN"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        region = await detect_region("203.0.113.5")  # non-local IP
    assert region == "IN"


@pytest.mark.asyncio
async def test_detect_region_us():
    from app.services.region_service import detect_region

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"countryCode": "US"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        region = await detect_region("8.8.8.8")
    assert region == "US"


@pytest.mark.asyncio
async def test_detect_region_eu():
    from app.services.region_service import detect_region

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"countryCode": "DE"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        region = await detect_region("1.2.3.4")
    assert region == "EU"


@pytest.mark.asyncio
async def test_detect_region_unknown_country_defaults_us():
    from app.services.region_service import detect_region

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"countryCode": "ZZ"}  # not mapped

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        region = await detect_region("1.2.3.4")
    assert region == "US"


@pytest.mark.asyncio
async def test_detect_region_api_error_defaults_us():
    from app.services.region_service import detect_region

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = Exception("network error")
        mock_client_cls.return_value = mock_client

        region = await detect_region("1.2.3.4")
    assert region == "US"


def test_is_local_ip_localhost():
    from app.services.region_service import _is_local_ip

    assert _is_local_ip("127.0.0.1") is True
    assert _is_local_ip("localhost") is True
    assert _is_local_ip("0.0.0.0") is True  # noqa: S104


def test_is_local_ip_private():
    from app.services.region_service import _is_local_ip

    assert _is_local_ip("192.168.1.1") is True
    assert _is_local_ip("10.0.0.1") is True


def test_is_local_ip_public():
    from app.services.region_service import _is_local_ip

    assert _is_local_ip("8.8.8.8") is False
    assert _is_local_ip("1.1.1.1") is False


def test_is_local_ip_empty():
    from app.services.region_service import _is_local_ip

    assert _is_local_ip("") is True


@pytest.mark.asyncio
async def test_resolve_user_region_uses_existing():
    from app.services.region_service import resolve_user_region

    user = make_user(region="IN")
    region = await resolve_user_region(user, None, None)
    assert region == "IN"
    assert user.region == "IN"


@pytest.mark.asyncio
async def test_resolve_user_region_explicit_override():
    from app.services.region_service import resolve_user_region

    user = make_user(region="IN")
    region = await resolve_user_region(user, None, None, explicit_region="US")
    assert region == "US"
