"""Unit tests for the text-svc entitlement gate client + brainfuck CPU bound.

Covers: allow/deny, fail-closed for billable tools when the gate is down,
fail-open for always-free tools, the client-IP helper, and the H-5 wall-clock
bound on the brainfuck interpreter.
"""

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.auth import OptionalUser
from app.services import entitlement_client as ec
from app.services.text_service import brainfuck_decode


def _req(headers: dict | None = None, ip: str = "198.51.100.9") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": raw,
            "client": (ip, 0),
            "query_string": b"",
        }
    )


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
    monkeypatch.setattr(ec.httpx, "AsyncClient", lambda *a, **k: _Client(resp, exc))


async def test_allowed_user_returns_none(monkeypatch):
    _patch(monkeypatch, resp=_Resp(200, {"allowed": True, "reason": "free"}))
    user = OptionalUser(id="u1", email="a@b.c", is_email_verified=True)
    assert (
        await ec.check_access(
            tool_id="uppercase", tool_type="local", request=_req(), user=user
        )
        is None
    )


async def test_denied_raises_402(monkeypatch):
    _patch(monkeypatch, resp=_Resp(200, {"allowed": False, "reason": "blocked"}))
    with pytest.raises(HTTPException) as exc:
        await ec.check_access(
            tool_id="uppercase", tool_type="local", request=_req(), user=None
        )
    assert exc.value.status_code == 402


async def test_unreachable_billable_fails_closed_503(monkeypatch):
    _patch(monkeypatch, exc=httpx.ConnectError("refused"))
    with pytest.raises(HTTPException) as exc:
        await ec.check_access(
            tool_id="uppercase", tool_type="local", request=_req(), user=None
        )
    assert exc.value.status_code == 503


async def test_unreachable_always_free_is_served(monkeypatch):
    _patch(monkeypatch, exc=httpx.ConnectError("refused"))
    # 'compare' is in the always-free allowlist — served even with the gate down.
    assert (
        await ec.check_access(
            tool_id="compare", tool_type="local", request=_req(), user=None
        )
        is None
    )


def test_client_ip_prefers_forwarded_for():
    assert (
        ec.client_ip(_req(headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"}))
        == "9.9.9.9"
    )
    assert ec.client_ip(_req()) == "198.51.100.9"


def test_brainfuck_infinite_loop_is_bounded():
    # '+[]' increments cell 0 to 1 then loops forever; it must raise (step/time
    # bound), not hang. Completes well under the 1s wall-clock cap.
    with pytest.raises(ValueError):
        brainfuck_decode("+[]")
