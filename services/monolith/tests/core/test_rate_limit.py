"""Tests for app/core/rate_limit.py — in-memory sliding window rate limiter."""

import time
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.rate_limit import InMemoryRateLimiter


def _make_request(host: str = "127.0.0.1") -> MagicMock:
    """Build a minimal Request-like mock."""
    request = MagicMock()
    request.client.host = host
    return request


class TestInMemoryRateLimiter:
    """Tests for the sliding-window in-memory rate limiter."""

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self):
        """Requests within the limit are allowed without raising."""
        limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)
        request = _make_request()
        for _ in range(5):
            await limiter.check(request)

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self):
        """Sixth request exceeds limit of 5 and raises HTTP 429."""
        limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)
        request = _make_request()
        for _ in range(5):
            await limiter.check(request)
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check(request)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_uses_user_key_when_provided(self):
        """When user_id is passed, uses user-based key instead of IP."""
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        request = _make_request("10.0.0.1")
        # Fill the limit for user-123
        await limiter.check(request, user_id="user-123")
        await limiter.check(request, user_id="user-123")
        # user-123 is now blocked
        with pytest.raises(HTTPException):
            await limiter.check(request, user_id="user-123")
        # But user-456 on the same IP is allowed
        await limiter.check(request, user_id="user-456")

    @pytest.mark.asyncio
    async def test_different_ips_tracked_separately(self):
        """Different IP addresses have independent rate limits."""
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        req1 = _make_request("10.0.0.1")
        req2 = _make_request("10.0.0.2")
        await limiter.check(req1)
        await limiter.check(req2)
        # Each IP used its 1 allowed request
        with pytest.raises(HTTPException):
            await limiter.check(req1)
        with pytest.raises(HTTPException):
            await limiter.check(req2)

    @pytest.mark.asyncio
    async def test_expired_entries_are_purged(self):
        """Entries outside the window are purged, freeing up the limit."""
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=1)
        request = _make_request()
        await limiter.check(request)
        await limiter.check(request)
        # Now at limit; inject old timestamps
        key = request.client.host
        limiter._hits[key] = [time.time() - 10, time.time() - 10]
        # Should succeed because old entries get purged
        await limiter.check(request)

    @pytest.mark.asyncio
    async def test_unknown_client_host_fallback(self):
        """Request with no client falls back to 'unknown' key."""
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        request = MagicMock()
        request.client = None
        await limiter.check(request)
        with pytest.raises(HTTPException):
            await limiter.check(request)

    @pytest.mark.asyncio
    async def test_default_settings_from_config(self):
        """Limiter without explicit params uses settings defaults."""
        limiter = InMemoryRateLimiter()
        from app.core.config import settings

        assert limiter.max_requests == settings.RATE_LIMIT_MAX_REQUESTS
        assert limiter.window_seconds == settings.RATE_LIMIT_WINDOW_SECONDS

    # -- Edge-case tests for the expiry / cleanup fix -----------------------

    @pytest.mark.asyncio
    async def test_rate_limit_allowed_after_expiry(self, monkeypatch):
        """After all hits expire, the next request must be ALLOWED (not 429).

        This was the original bug: expired timestamps caused the key to be
        deleted, which then skipped the rate check and raised no error, but
        with ``defaultdict`` the empty list was silently re-created and the
        new hit was never recorded properly.  The fix ensures that after
        pruning, the rate check sees an empty (or absent) list and correctly
        allows the request.
        """
        fake_time = [1000.0]
        monkeypatch.setattr(time, "time", lambda: fake_time[0])

        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=10)
        request = _make_request("192.168.1.1")

        # Use up the full quota.
        await limiter.check(request)
        await limiter.check(request)

        # Advance time so all hits are outside the window.
        fake_time[0] = 1020.0

        # The next request must succeed — expired hits should not block.
        await limiter.check(request)  # no HTTPException expected

    @pytest.mark.asyncio
    async def test_memory_cleanup_after_expiry(self, monkeypatch):
        """Once all timestamps for a key expire, the key is removed from _hits."""
        fake_time = [1000.0]
        monkeypatch.setattr(time, "time", lambda: fake_time[0])

        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=5)
        request = _make_request("10.10.10.10")

        await limiter.check(request)
        await limiter.check(request)

        key = "10.10.10.10"
        assert key in limiter._hits

        # Advance past the window so every timestamp is expired.
        fake_time[0] = 1010.0

        # Trigger pruning by performing another check.
        await limiter.check(request)

        # After the check, the old key should have been deleted during
        # pruning and a fresh entry created for the new hit.  The list
        # should contain exactly the one new timestamp.
        assert key in limiter._hits
        assert len(limiter._hits[key]) == 1
        assert limiter._hits[key][0] == 1010.0

    @pytest.mark.asyncio
    async def test_rate_limit_actually_blocks(self):
        """Filling up to max_requests and then making one more must raise 429."""
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        request = _make_request("172.16.0.1")

        for _ in range(3):
            await limiter.check(request)

        with pytest.raises(HTTPException) as exc_info:
            await limiter.check(request)
        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_different_keys_are_independent(self):
        """User A hitting the limit must not affect User B."""
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        req_a = _make_request("10.0.0.1")
        req_b = _make_request("10.0.0.2")

        # User A exhausts quota.
        await limiter.check(req_a, user_id="user-A")
        with pytest.raises(HTTPException):
            await limiter.check(req_a, user_id="user-A")

        # User B is completely unaffected.
        await limiter.check(req_b, user_id="user-B")

        # And a bare-IP request from A's address is also independent of the
        # user-keyed limits.
        await limiter.check(req_a)
