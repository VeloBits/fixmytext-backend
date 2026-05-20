"""Test configuration and fixtures for account-svc."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure the app can import without a real DB
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/testdb"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters")


@pytest.fixture
def app():
    """Return the FastAPI application instance."""
    from main import app as _app

    return _app


@pytest.fixture
async def async_client(app):
    """Async HTTP client for testing FastAPI endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
