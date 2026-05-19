"""
Integration tests for text-svc endpoints.

Uses httpx AsyncClient against the FastAPI app directly — no mocks needed
because text transforms are pure stdlib functions.
"""

import pytest


@pytest.mark.asyncio
async def test_health(client):
    """GET /health should return 200 with status ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "text-svc"


@pytest.mark.asyncio
async def test_uppercase(client):
    """POST /api/v1/text/uppercase should uppercase the input text."""
    resp = await client.post(
        "/api/v1/text/uppercase",
        json={"text": "hello"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "HELLO"
    assert data["original"] == "hello"
    assert data["operation"] == "uppercase"


@pytest.mark.asyncio
async def test_reverse_text(client):
    """POST /api/v1/text/reverse should reverse the input text."""
    resp = await client.post(
        "/api/v1/text/reverse",
        json={"text": "hello"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "olleh"
    assert data["original"] == "hello"
    assert data["operation"] == "reverse"


@pytest.mark.asyncio
async def test_nonexistent_tool(client):
    """POST /api/v1/text/nonexistent-tool should return 404."""
    resp = await client.post(
        "/api/v1/text/nonexistent-tool",
        json={"text": "hello"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_caesar_cipher(client):
    """POST /api/v1/text/caesar-cipher with shift=1 should shift letters by 1."""
    resp = await client.post(
        "/api/v1/text/caesar-cipher",
        json={"text": "abc", "shift": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == "bcd"
    assert data["original"] == "abc"
    assert data["operation"] == "caesar-cipher"
