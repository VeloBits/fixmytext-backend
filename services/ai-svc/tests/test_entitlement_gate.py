"""Unit tests for the ai-svc entitlement gate client.

AI tools are always billable, so the gate fails CLOSED (503) when payments-svc is
unreachable or errors, and returns 402 when quota is exhausted.
"""

import httpx
import pytest
from fastapi import HTTPException

from app.services import entitlement_client as ec


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _Client:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, *_a, **_k):
        if self._exc is not None:
            raise self._exc
        return self._resp


def _patch(monkeypatch, resp=None, exc=None):
    monkeypatch.setattr(ec, "_HTTP_CLIENT", _Client(resp, exc))


async def test_allowed_returns_none(monkeypatch):
    _patch(monkeypatch, resp=_Resp(200, {"allowed": True, "reason": "credit"}))
    assert await ec.check_entitlement(tool_id="summarize", user_id="u1") is None


async def test_denied_raises_402(monkeypatch):
    _patch(
        monkeypatch,
        resp=_Resp(200, {"allowed": False, "reason": "blocked", "message": "no quota"}),
    )
    with pytest.raises(HTTPException) as exc:
        await ec.check_entitlement(tool_id="summarize", user_id="u1")
    assert exc.value.status_code == 402


async def test_gate_5xx_fails_closed_503(monkeypatch):
    _patch(monkeypatch, resp=_Resp(500, {}))
    with pytest.raises(HTTPException) as exc:
        await ec.check_entitlement(tool_id="summarize", user_id="u1")
    assert exc.value.status_code == 503


async def test_gate_unreachable_fails_closed_503(monkeypatch):
    _patch(monkeypatch, exc=httpx.ConnectError("connection refused"))
    with pytest.raises(HTTPException) as exc:
        await ec.check_entitlement(tool_id="summarize", user_id="u1")
    assert exc.value.status_code == 503


# ── HTTP client lifecycle ─────────────────────────────────────────────────────


async def test_init_and_close_http_client(monkeypatch):
    monkeypatch.setattr(ec, "_HTTP_CLIENT", None)

    ec.init_http_client()
    assert isinstance(ec._HTTP_CLIENT, httpx.AsyncClient)

    await ec.close_http_client()
    assert ec._HTTP_CLIENT is None


async def test_close_http_client_noop_when_uninitialised(monkeypatch):
    monkeypatch.setattr(ec, "_HTTP_CLIENT", None)
    await ec.close_http_client()
    assert ec._HTTP_CLIENT is None


async def test_get_http_client_creates_lazily_and_reuses(monkeypatch):
    monkeypatch.setattr(ec, "_HTTP_CLIENT", None)

    first = ec._get_http_client()
    assert isinstance(first, httpx.AsyncClient)
    assert ec._get_http_client() is first

    await ec.close_http_client()
    assert ec._HTTP_CLIENT is None
