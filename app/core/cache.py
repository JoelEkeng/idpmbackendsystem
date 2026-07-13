"""Lightweight async Redis caching helpers.

Usage:
    from app.core.cache import cache_get_json, cache_set_json, cache_delete

    cached = await cache_get_json(key)
    if cached is not None:
        return cached
    data = await expensive_query()
    await cache_set_json(key, data, ttl=30)

All helpers are fail-open: if Redis is unavailable the app keeps working
(just uncached) instead of raising. This keeps a Redis outage from taking
down the API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.redis import redis_client

logger = logging.getLogger(__name__)


async def cache_get_json(key: str) -> Any | None:
    """Return the decoded JSON value for `key`, or None on miss/error."""
    try:
        raw = await redis_client.get(key)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Redis GET failed for %s: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def cache_set_json(key: str, value: Any, ttl: int = 30) -> None:
    """Store `value` as JSON under `key` with a TTL in seconds. Fail-open."""
    try:
        await redis_client.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Redis SET failed for %s: %s", key, exc)


async def cache_delete(*keys: str) -> None:
    """Delete one or more keys. Fail-open."""
    if not keys:
        return
    try:
        await redis_client.delete(*keys)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Redis DELETE failed for %s: %s", keys, exc)


async def cache_delete_prefix(prefix: str) -> None:
    """Delete every key matching `prefix*` using non-blocking SCAN. Fail-open."""
    try:
        async for key in redis_client.scan_iter(match=f"{prefix}*", count=100):
            await redis_client.delete(key)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Redis prefix delete failed for %s: %s", prefix, exc)
