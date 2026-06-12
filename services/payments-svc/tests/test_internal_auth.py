"""Unit tests for the internal-secret guard and server-derived visitor key.

No database required.
"""

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import internal as internal_ep
from app.core import deps


async def test_verify_internal_secret_accepts_match(monkeypatch):
    monkeypatch.setattr(deps.settings, "INTERNAL_SHARED_SECRET", "s3cret")
    assert await deps.verify_internal_secret(x_internal_secret="s3cret") is None


async def test_verify_internal_secret_rejects_wrong(monkeypatch):
    monkeypatch.setattr(deps.settings, "INTERNAL_SHARED_SECRET", "s3cret")
    with pytest.raises(HTTPException) as exc:
        await deps.verify_internal_secret(x_internal_secret="nope")
    assert exc.value.status_code == 401


async def test_verify_internal_secret_fails_closed_when_unset(monkeypatch):
    """An unset secret denies every call so the gate is never silently open."""
    monkeypatch.setattr(deps.settings, "INTERNAL_SHARED_SECRET", "")
    with pytest.raises(HTTPException) as exc:
        await deps.verify_internal_secret(x_internal_secret="")
    assert exc.value.status_code == 401


def test_visitor_key_is_deterministic_and_ip_ua_bound():
    a = internal_ep._visitor_key("1.2.3.4", "UA/1.0")
    b = internal_ep._visitor_key("1.2.3.4", "UA/1.0")
    c = internal_ep._visitor_key("9.9.9.9", "UA/1.0")
    assert a == b  # same IP+UA -> same key
    assert a != c  # different IP -> different key
    assert len(a) == 64  # sha256 hexdigest
