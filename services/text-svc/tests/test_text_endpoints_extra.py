"""Endpoint tests for parameterized tool schemas and dispatcher error paths.

Complements test_text_endpoints.py: covers every request model that carries
extra arguments (shift, key, rails, delimiter, ...) plus the 400/404 error
handling in the central ``_execute_tool`` dispatcher.

The rate limiter is patched out for the whole module — these tests add enough
requests to exhaust the shared in-memory visitor window otherwise.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.endpoints import text as text_module
from app.tool_registry import ToolDefinition, ToolType


@pytest.fixture(autouse=True)
def _no_rate_limit():
    """Patch the rate limiter so this module never trips the visitor window."""
    with patch(
        "app.api.v1.endpoints.text.text_limiter",
        new=MagicMock(check=AsyncMock()),
    ):
        yield


def _asgi_request() -> Request:
    """Bare Starlette request for direct calls into ``_execute_tool``."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": ("198.51.100.7", 0),
            "query_string": b"",
        }
    )


# ── Tools with extra request parameters ──────────────────────────────────


@pytest.mark.asyncio
async def test_vigenere_encrypt_endpoint(client):
    resp = await client.post(
        "/api/v1/text/vigenere-encrypt",
        json={"text": "ATTACKATDAWN", "key": "LEMON"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "LXFOPVEFRNHR"


@pytest.mark.asyncio
async def test_vigenere_decrypt_endpoint(client):
    resp = await client.post(
        "/api/v1/text/vigenere-decrypt",
        json={"text": "LXFOPVEFRNHR", "key": "LEMON"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "ATTACKATDAWN"


@pytest.mark.asyncio
async def test_rail_fence_encrypt_endpoint(client):
    resp = await client.post(
        "/api/v1/text/rail-fence-encrypt",
        json={"text": "WEAREDISCOVEREDFLEEATONCE", "rails": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "WECRLTEERDSOEEFEAOCAIVDEN"


@pytest.mark.asyncio
async def test_rail_fence_decrypt_endpoint(client):
    resp = await client.post(
        "/api/v1/text/rail-fence-decrypt",
        json={"text": "WECRLTEERDSOEEFEAOCAIVDEN", "rails": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "WEAREDISCOVEREDFLEEATONCE"


@pytest.mark.asyncio
async def test_playfair_encrypt_endpoint(client):
    resp = await client.post(
        "/api/v1/text/playfair-encrypt",
        json={"text": "hide the gold in the tree stump", "key": "playfair example"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "BMODZBXDNABEKUDMUIXMMOUVIF"


@pytest.mark.asyncio
async def test_substitution_cipher_endpoint(client):
    resp = await client.post(
        "/api/v1/text/substitution-cipher",
        json={"text": "abc", "mapping": "QWERTYUIOPASDFGHJKLZXCVBNM"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "qwe"


@pytest.mark.asyncio
async def test_columnar_transposition_endpoint(client):
    resp = await client.post(
        "/api/v1/text/columnar-transposition",
        json={"text": "HELLOWORLD", "key": "KEY"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "EOR HLODLWL "


@pytest.mark.asyncio
async def test_split_to_lines_endpoint(client):
    resp = await client.post(
        "/api/v1/text/split-to-lines",
        json={"text": "a;b;c", "delimiter": ";"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "a\nb\nc"


@pytest.mark.asyncio
async def test_join_lines_endpoint(client):
    resp = await client.post(
        "/api/v1/text/join-lines",
        json={"text": "a\nb", "delimiter": "-"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "a-b"


@pytest.mark.asyncio
async def test_pad_lines_endpoint(client):
    resp = await client.post(
        "/api/v1/text/pad-lines",
        json={"text": "a\nbbb", "align": "right"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "  a\nbbb"


@pytest.mark.asyncio
async def test_wrap_lines_endpoint(client):
    resp = await client.post(
        "/api/v1/text/wrap-lines",
        json={"text": "a\nb", "prefix": "<", "suffix": ">"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "<a>\n<b>"


@pytest.mark.asyncio
async def test_filter_lines_endpoint(client):
    resp = await client.post(
        "/api/v1/text/filter-lines",
        json={"text": "apple\nbanana\ncherry", "pattern": "an"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "banana"


@pytest.mark.asyncio
async def test_remove_lines_regex_endpoint(client):
    resp = await client.post(
        "/api/v1/text/remove-lines",
        json={"text": "apple\nbanana", "pattern": "^a", "use_regex": True},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "banana"


@pytest.mark.asyncio
async def test_filter_lines_invalid_regex_rejected(client):
    """A malformed regex must fail schema validation with 422."""
    resp = await client.post(
        "/api/v1/text/filter-lines",
        json={"text": "apple", "pattern": "[unclosed", "use_regex": True},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_truncate_lines_endpoint(client):
    resp = await client.post(
        "/api/v1/text/truncate-lines",
        json={"text": "abcdef", "max_length": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "abcd…"


@pytest.mark.asyncio
async def test_extract_nth_lines_endpoint(client):
    resp = await client.post(
        "/api/v1/text/extract-nth-lines",
        json={"text": "a\nb\nc\nd", "n": 2, "offset": 1},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == "b\nd"


# ── Dispatcher error paths ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_tool_unknown_id_raises_404():
    """The dispatcher 404s on an unregistered tool id (defence in depth)."""
    with pytest.raises(HTTPException) as exc:
        await text_module._execute_tool("no-such-tool", _asgi_request(), None, None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_decode_error_maps_to_400(client):
    """Registry error_exceptions surface as 400 with the tool's error_detail."""
    resp = await client.post(
        "/api/v1/text/base64-decode",
        json={"text": "!!!not-base64!!!"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid Base64 input"


@pytest.mark.asyncio
async def test_redos_pattern_returns_400(client):
    """A catastrophically backtracking regex hits the ReDoS budget → 400."""
    resp = await client.post(
        "/api/v1/text/filter-lines",
        json={
            "text": "a" * 1999 + "b",
            "pattern": "(a+)+$",
            "use_regex": True,
        },
    )
    assert resp.status_code == 400
    assert "budget" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_tool_timeout_returns_400(client):
    """A handler exceeding the wall-clock cap returns 400, not 500."""
    with patch.object(text_module, "_TOOL_EXEC_TIMEOUT_SECONDS", 0):
        resp = await client.post(
            "/api/v1/text/uppercase",
            json={"text": "hello"},
        )
    assert resp.status_code == 400
    assert "too expensive" in resp.json()["detail"]


def _fake_tool(handler, error_exceptions=()):
    return ToolDefinition(
        id="uppercase",
        handler=handler,
        tool_type=ToolType.LOCAL,
        display_name="Fake Uppercase",
        error_exceptions=error_exceptions,
    )


@pytest.mark.asyncio
async def test_http_exception_from_handler_passes_through(client):
    """An HTTPException raised inside the handler is re-raised unchanged."""

    def _handler(_text):
        raise HTTPException(status_code=418, detail="teapot")

    with patch.object(text_module, "get_tool", return_value=_fake_tool(_handler)):
        resp = await client.post("/api/v1/text/uppercase", json={"text": "x"})
    assert resp.status_code == 418
    assert resp.json()["detail"] == "teapot"


@pytest.mark.asyncio
async def test_unexpected_handler_error_propagates(client):
    """Errors not in the tool's error_exceptions are NOT converted to 400."""

    def _handler(_text):
        raise RuntimeError("boom")

    with (
        patch.object(text_module, "get_tool", return_value=_fake_tool(_handler)),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await client.post("/api/v1/text/uppercase", json={"text": "x"})
