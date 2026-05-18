"""In-memory sliding-window rate limiter (single-instance fallback)."""

import logging
import time

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Sliding-window rate limiter backed by an in-memory dict.

    Keys are either ``user:<user_id>`` (for authenticated requests) or the
    client IP address. Expired timestamps are purged on every check.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}

    async def check(self, request: Request, user_id: str | None = None) -> None:
        """Check rate limit. Raises HTTPException(429) if exceeded."""
        if user_id:
            key = f"user:{user_id}"
        else:
            key = request.client.host if request.client else "unknown"

        now = time.time()

        if key in self._hits:
            self._hits[key] = [
                t for t in self._hits[key] if now - t < self.window_seconds
            ]
            if not self._hits[key]:
                del self._hits[key]

        current = self._hits.get(key, [])
        if len(current) >= self.max_requests:
            logger.warning(
                "RATE LIMIT hit for %s (%d/%d in %ds)",
                key,
                len(current),
                self.max_requests,
                self.window_seconds,
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again shortly.",
            )

        self._hits.setdefault(key, []).append(now)
