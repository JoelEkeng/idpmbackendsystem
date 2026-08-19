"""Custom ASGI/HTTP middleware: security headers + Redis-backed rate limiting.

The rate limiter uses a fixed-window counter in Redis keyed by client IP, so it
works across multiple API workers/instances (unlike an in-process limiter).
It is fail-open: if Redis is unreachable, requests are allowed through rather
than blocking all traffic.
"""

from __future__ import annotations

import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.redis import redis_client
from app.utils.network import get_client_ip

logger = logging.getLogger(__name__)


def _parse_rate(rate: str) -> tuple[int, int]:
    """Parse a '<count>/<period>' string into (limit, window_seconds)."""
    periods = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    try:
        count_str, period = rate.split("/")
        return int(count_str), periods.get(period.strip().lower(), 60)
    except (ValueError, AttributeError):
        return 100, 60


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard hardening headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter backed by Redis, keyed by client IP."""

    # Sensitive prefixes get a tighter limit than the global default,
    # regardless of what RATE_LIMIT is set to.
    STRICT_PREFIXES: dict[str, str] = {
        "/api/v1/finance": "20/minute",
        "/api/v1/attendance/checkin": "60/minute",
        # Includes both public registration (POST) and admin listing (GET),
        # since the limiter is path- not method-based. Tighter than the
        # default since registration has no login gating it.
        "/api/v1/visitors": "20/minute",
    }

    def __init__(self, app, rate: str = "100/minute", exempt_paths: tuple[str, ...] = ()):
        super().__init__(app)
        self.limit, self.window = _parse_rate(rate)
        self.exempt_paths = exempt_paths
        self.strict_limits = {
            prefix: _parse_rate(r) for prefix, r in self.STRICT_PREFIXES.items()
        }

    def _limit_for(self, path: str) -> tuple[str, int, int]:
        for prefix, (limit, window) in self.strict_limits.items():
            if path.startswith(prefix):
                return prefix, limit, window
        return "default", self.limit, self.window

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in self.exempt_paths):
            return await call_next(request)

        bucket, limit, window = self._limit_for(path)
        ip = get_client_ip(request)
        window_id = int(time.time()) // window
        key = f"ratelimit:{bucket}:{ip}:{window_id}"

        try:
            current = await redis_client.incr(key)
            if current == 1:
                await redis_client.expire(key, window)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Rate limiter unavailable, allowing request: %s", exc)
            return await call_next(request)

        if current > limit:
            retry_after = window - (int(time.time()) % window)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current))
        return response
