"""Test configuration and fixtures for text-svc tests."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def mock_entitlement_client():
    """Auto-mock the entitlement client so tests don't need a live payments-svc.

    Individual tests that want to control entitlement behaviour (e.g. raise 402)
    can patch 'app.api.v1.endpoints.text.check_entitlement' themselves - their
    inner patch takes precedence over this fixture's outer one.
    """
    with patch(
        "app.api.v1.endpoints.text.check_entitlement",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


@pytest.fixture
async def client():
    """Async HTTP client connected directly to the FastAPI app (no real server)."""
    # Import here so env vars are read before app init
    from main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
