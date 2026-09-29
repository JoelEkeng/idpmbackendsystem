from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse, Response

import main
from app.api.v1.router import equipment
from app.core import cache, middleware
from app.core.config import get_settings
from app.utils import network


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError("unavailable")

    async def set(self, *args, **kwargs):
        raise ConnectionError("unavailable")

    async def delete(self, *keys):
        raise ConnectionError("unavailable")

    def scan_iter(self, **kwargs):
        async def items():
            raise ConnectionError("unavailable")
            yield

        return items()


@pytest.mark.asyncio
async def test_cache_helpers_fail_open_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(cache, "redis_client", BrokenRedis())

    assert await cache.cache_get_json("key") is None
    await cache.cache_set_json("key", {"value": 1})
    await cache.cache_delete("key")
    await cache.cache_delete_prefix("prefix:")


def test_equipment_cache_key_includes_pagination():
    assert equipment._equipment_cache_key(100, 0) != equipment._equipment_cache_key(100, 100)
    assert equipment._equipment_cache_key(50, 0) != equipment._equipment_cache_key(100, 0)


class RateRedis:
    def __init__(self):
        self.values = {}
        self.calls = []

    async def eval(self, script, keys, key, window):
        self.calls.append((script, keys, key, window))
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]


def make_request(path="/api/v1/services", client="203.0.113.10", headers=None):
    raw_headers = [
        (name.lower().encode(), value.encode())
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": raw_headers,
            "client": (client, 1234),
            "scheme": "https",
            "server": ("test", 443),
            "query_string": b"",
        }
    )


@pytest.mark.asyncio
async def test_rate_limit_uses_atomic_redis_counter_and_returns_429(monkeypatch):
    redis = RateRedis()
    monkeypatch.setattr(middleware, "redis_client", redis)
    limiter = middleware.RateLimitMiddleware(lambda scope, receive, send: None, rate="2/minute")

    async def call_next(request):
        return Response(status_code=200)

    first = await limiter.dispatch(make_request(), call_next)
    second = await limiter.dispatch(make_request(), call_next)
    third = await limiter.dispatch(make_request(), call_next)

    assert first.status_code == second.status_code == 200
    assert third.status_code == 429
    assert third.headers["Retry-After"]
    assert all("INCR" in call[0] and "EXPIRE" in call[0] for call in redis.calls)
    assert all(call[1] == 1 for call in redis.calls)


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_redis_is_unavailable(monkeypatch):
    class Redis:
        async def eval(self, *args):
            raise ConnectionError("unavailable")

    monkeypatch.setattr(middleware, "redis_client", Redis())
    limiter = middleware.RateLimitMiddleware(lambda scope, receive, send: None)

    async def call_next(request):
        return Response(status_code=204)

    response = await limiter.dispatch(make_request(), call_next)
    assert response.status_code == 204


def test_client_ip_only_trusts_forwarded_header_when_configured(monkeypatch):
    request = make_request(headers={"x-forwarded-for": "198.51.100.7, 10.0.0.1"})

    monkeypatch.setattr(network, "get_settings", lambda: SimpleNamespace(TRUST_PROXY_HEADERS=False))
    assert network.get_client_ip(request) == "203.0.113.10"

    monkeypatch.setattr(network, "get_settings", lambda: SimpleNamespace(TRUST_PROXY_HEADERS=True))
    assert network.get_client_ip(request) == "198.51.100.7"


@pytest.mark.asyncio
async def test_readiness_reports_dependency_failure(monkeypatch):
    async def database_ready():
        return True

    async def redis_ready():
        return False

    monkeypatch.setattr(main, "_database_ready", database_ready)
    monkeypatch.setattr(main, "_redis_ready", redis_ready)

    response = await main.readiness()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert b'"database":"ok"' in response.body
    assert b'"redis":"unavailable"' in response.body


@pytest.mark.asyncio
async def test_readiness_reports_ready(monkeypatch):
    async def ready():
        return True

    monkeypatch.setattr(main, "_database_ready", ready)
    monkeypatch.setattr(main, "_redis_ready", ready)

    response = await main.readiness()

    assert response["status"] == "ready"
    assert response["dependencies"] == {"database": "ok", "redis": "ok"}


def test_safe_observability_and_paystack_defaults():
    settings = get_settings()
    assert settings.SENTRY_SEND_DEFAULT_PII is False
    assert 0 <= settings.SENTRY_TRACES_SAMPLE_RATE <= 1
    assert settings.PAYSTACK_BASE_URL.startswith("https://")
    assert settings.PAYSTACK_TIMEOUT_SECONDS > 0
