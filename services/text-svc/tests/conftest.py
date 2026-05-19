"""Test configuration and fixtures for text-svc tests."""

import pytest
from httpx import ASGITransport, AsyncClient


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
