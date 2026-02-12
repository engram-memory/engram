"""Rate limiting middleware using in-memory sliding window."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from server.auth.dependencies import CLOUD_MODE


class _SlidingWindow:
    """Simple sliding window rate limiter. No external dependencies."""

    def __init__(self):
        # {user_id: [(timestamp, count_in_window)]}
        self._windows: dict[str, list[float]] = defaultdict(list)

    def check(self, user_id: str, limit: int, window_seconds: int = 1) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, remaining)."""
        if limit <= 0:  # 0 = unlimited
            return True, 999

        now = time.monotonic()
        cutoff = now - window_seconds
        hits = self._windows[user_id]

        # Prune old entries
        self._windows[user_id] = [t for t in hits if t > cutoff]
        hits = self._windows[user_id]

        if len(hits) >= limit:
            return False, 0

        hits.append(now)
        return True, limit - len(hits)


_limiter = _SlidingWindow()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-user rate limiting based on tier."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not CLOUD_MODE:
            return await call_next(request)

        # Skip rate limiting for auth routes and health
        if request.url.path.startswith("/v1/auth") or request.url.path == "/v1/health":
            return await call_next(request)

        # Get user from state (set by auth dependency)
        user = getattr(request.state, "auth_user", None)
        if user is None:
            return await call_next(request)

        limit = user.limits.requests_per_second
        allowed, remaining = _limiter.check(user.id, limit)

        if not allowed:
            raise HTTPException(
                429,
                detail="Rate limit exceeded. Upgrade your plan for higher limits.",
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "1",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
