"""Shared pytest configuration for fixmytext-shared tests."""

import pytest


@pytest.fixture
def request_factory():
    """Build a minimal stub Request object with a client attribute."""
    from unittest.mock import MagicMock

    def _build(host: str = "1.2.3.4"):
        req = MagicMock()
        req.client.host = host
        return req

    return _build
