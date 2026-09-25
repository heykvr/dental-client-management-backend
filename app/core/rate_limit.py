"""Per-client-IP rate limiting with a sliding window, as FastAPI dependencies.

The default limit is attached to the whole /api/v1 router, so every API endpoint is covered
(including future ones); /health lives outside it and is therefore exempt. AI routes add
their own stricter limit on top.
"""

import math
import time

from fastapi import Depends, Request
from limits import parse_many
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from app.core.config import get_settings
from app.core.exceptions import RateLimitedError

# moving-window = sliding window: counts requests in the last N seconds, so bursts across a
# fixed-window boundary are impossible. In-memory store is fine for a single instance
# (a Redis store would be needed for several instances; noted in README).
_storage = MemoryStorage()
_limiter = MovingWindowRateLimiter(_storage)


def get_client_ip(request: Request) -> str:
    """The real client IP behind Render's proxy.

    Render appends the connecting IP to X-Forwarded-For, so the RIGHTMOST entry is trustworthy.
    The leftmost entries come from the client and can be faked to dodge the limit, so they
    are ignored. Without the header (local dev), use the direct connection's IP.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    if entries:
        return entries[-1]
    return request.client.host if request.client else "unknown"


def rate_limit(limit_string: str, scope: str):
    """Dependency enforcing e.g. "3/minute;20/day" per client IP. `scope` names the bucket."""
    limit_items = parse_many(limit_string)

    async def check(request: Request) -> None:
        client_ip = get_client_ip(request)
        # Test every limit before counting, so a rejected request uses up nothing
        for item in limit_items:
            if not _limiter.test(item, scope, client_ip):
                reset_at, _remaining = _limiter.get_window_stats(item, scope, client_ip)
                retry_after = max(1, math.ceil(reset_at - time.time()))
                raise RateLimitedError(
                    f"Too many requests. Please try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
        for item in limit_items:
            _limiter.hit(item, scope, client_ip)

    return Depends(check)


def reset_rate_limits() -> None:
    """Clear all counters (used by tests)."""
    _storage.reset()


settings = get_settings()
default_rate_limit = rate_limit(settings.rate_limit_default, "default")
ai_rate_limit = rate_limit(settings.rate_limit_ai, "ai")
