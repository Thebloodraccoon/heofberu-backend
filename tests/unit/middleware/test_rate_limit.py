"""
Unit tests for the per-IP rate limiting middleware.

``RateLimitMiddleware`` is driven through ``dispatch`` with a stubbed
Starlette request and an async ``call_next``. Redis is faked via an async
context manager patched onto ``settings.get_redis`` (never a real server),
and ``time.time`` is frozen inside the middleware module for deterministic
fixed/sliding windows.
"""

from collections import deque
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace

from fastapi.responses import Response
import pytest
from starlette import status
from starlette.datastructures import Headers

import app.middleware.rate_limit as rate_limit_module
from app.middleware.rate_limit import _MAX_TRACKED_CLIENTS, RateLimitMiddleware
from app.middleware.utils import get_client_ip
from app.settings import settings


class FakeRedis:
    """Minimal async Redis stand-in recording ``incr``/``expire`` calls."""

    def __init__(self, incr_result=1):
        self.incr_result = incr_result
        self.incr_calls = []
        self.expire_calls = []

    async def incr(self, key):
        self.incr_calls.append(key)
        return self.incr_result

    async def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))


class FrozenTime:
    """Stand-in for the ``time`` module with a fixed ``time()`` value."""

    def __init__(self, now):
        self.now = now

    def time(self):
        return self.now


def make_redis(monkeypatch, store):
    @asynccontextmanager
    async def get_redis():
        yield store

    monkeypatch.setattr(settings, "get_redis", lambda: get_redis())


def make_request(path="/api/things", headers=None, client_host="10.0.0.1"):
    request = SimpleNamespace()
    request.url = SimpleNamespace(path=path)
    request.headers = Headers(headers or {})
    request.client = SimpleNamespace(host=client_host) if client_host else None
    return request


async def run_dispatch(middleware, request):
    seen = []

    async def call_next(req):
        seen.append(req)
        return Response("ok")

    response = await middleware.dispatch(request, call_next)
    return response, seen


def make_middleware(calls=5, period=60, skip_paths=None, now=None, monkeypatch=None):
    if now is not None and monkeypatch is not None:
        monkeypatch.setattr(rate_limit_module, "time", FrozenTime(now))
    return RateLimitMiddleware(app=SimpleNamespace(), calls=calls, period=period, skip_paths=skip_paths)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDispatchSkipPaths:
    async def test_skipped_path_bypasses_counting_and_call_next_runs(self, monkeypatch):
        store = FakeRedis()
        make_redis(monkeypatch, store)
        middleware = make_middleware(skip_paths=["/health"], monkeypatch=monkeypatch)

        response, seen = await run_dispatch(middleware, make_request(path="/health"))

        assert len(seen) == 1
        assert response.status_code == status.HTTP_200_OK
        assert "X-RateLimit-Limit" not in response.headers
        assert middleware.clients == {}
        assert store.incr_calls == []

    async def test_default_skip_paths_include_ping_and_health(self, monkeypatch):
        store = FakeRedis()
        make_redis(monkeypatch, store)
        middleware = make_middleware(monkeypatch=monkeypatch)

        for path in ("/ping", "/health"):
            _, seen = await run_dispatch(middleware, make_request(path=path))
            assert len(seen) == 1

        assert store.incr_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestDispatchUnderLimit:
    async def test_passes_through_with_rate_limit_headers(self, monkeypatch):
        store = FakeRedis(incr_result=2)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        response, seen = await run_dispatch(middleware, make_request())

        assert len(seen) == 1
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "3"
        assert response.headers["X-RateLimit-Reset"] == "1020"

    async def test_remaining_never_goes_negative(self, monkeypatch):
        store = FakeRedis(incr_result=99)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        response, _ = await run_dispatch(middleware, make_request())

        assert response.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.unit
@pytest.mark.asyncio
class TestDispatchOverLimit:
    async def test_returns_429_json_with_headers_and_call_next_not_called(self, monkeypatch):
        store = FakeRedis(incr_result=6)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        response, seen = await run_dispatch(middleware, make_request())

        assert len(seen) == 0
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert '"type":"rate_limit_exceeded"' in response.body.decode()
        assert json.loads(response.body)["error"]["status_code"] == 429
        assert response.headers["Retry-After"] == "20"
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Reset"] == "1020"


@pytest.mark.unit
@pytest.mark.asyncio
class TestCountAndCheckRedis:
    async def test_first_incr_in_window_sets_expiry(self, monkeypatch):
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        count, allowed = await middleware._count_and_check("1.2.3.4", 1000.0)

        assert count == 1
        assert allowed is True
        assert store.incr_calls == ["rate_limit:1.2.3.4:16"]
        assert store.expire_calls == [("rate_limit:1.2.3.4:16", 120)]

    async def test_subsequent_incr_does_not_reset_expiry(self, monkeypatch):
        store = FakeRedis(incr_result=7)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        count, allowed = await middleware._count_and_check("1.2.3.4", 1000.0)

        assert count == 7
        assert allowed is False
        assert store.incr_calls == ["rate_limit:1.2.3.4:16"]
        assert store.expire_calls == []

    async def test_window_number_is_derived_from_time(self, monkeypatch):
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=30, now=61.9, monkeypatch=monkeypatch)

        await middleware._count_and_check("1.2.3.4", 61.9)

        assert store.incr_calls == ["rate_limit:1.2.3.4:2"]

    async def test_count_equal_to_limit_is_allowed(self, monkeypatch):
        store = FakeRedis(incr_result=5)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        _, allowed = await middleware._count_and_check("1.2.3.4", 1000.0)

        assert allowed is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestRedisFailureFallback:
    async def test_broken_redis_falls_back_to_local_counters(self, monkeypatch):
        @asynccontextmanager
        async def broken_redis():
            raise ConnectionError("down")
            yield

        monkeypatch.setattr(settings, "get_redis", lambda: broken_redis())
        middleware = make_middleware(calls=2, period=60, now=1000.0, monkeypatch=monkeypatch)

        count, allowed = await middleware._count_and_check("1.2.3.4", 1000.0)

        assert count == 1
        assert allowed is True
        assert middleware.clients["1.2.3.4"] == deque([1000.0])

    async def test_dispatch_survives_broken_redis(self, monkeypatch):
        @asynccontextmanager
        async def broken_redis():
            raise ConnectionError("down")
            yield

        monkeypatch.setattr(settings, "get_redis", lambda: broken_redis())
        middleware = make_middleware(calls=2, period=60, now=1000.0, monkeypatch=monkeypatch)

        response, seen = await run_dispatch(middleware, make_request())

        assert len(seen) == 1
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
class TestLocalIncrAndCheck:
    def test_evicts_timestamps_older_than_window(self, monkeypatch):
        monkeypatch.setattr(rate_limit_module, "time", FrozenTime(1000.0))
        middleware = make_middleware(calls=5, period=60)
        middleware.clients["1.2.3.4"] = deque([900.0, 930.0])

        count, allowed = middleware._local_incr_and_check("1.2.3.4", 1000.0)

        assert count == 1
        assert allowed is True
        assert middleware.clients["1.2.3.4"] == deque([1000.0])

    def test_blocks_at_limit_boundary(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=2, period=60)

        assert middleware._local_incr_and_check("ip", 10.0) == (1, True)
        assert middleware._local_incr_and_check("ip", 11.0) == (2, True)
        assert middleware._local_incr_and_check("ip", 12.0) == (2, False)

    def test_blocked_requests_do_not_append_timestamps(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=1, period=60)

        assert middleware._local_incr_and_check("ip", 10.0) == (1, True)
        for tick in (11.0, 30.0, 59.9):
            _, allowed = middleware._local_incr_and_check("ip", tick)
            assert allowed is False

        assert list(middleware.clients["ip"]) == [10.0]

    def test_blocked_empty_history_entry_is_removed(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=0, period=60)

        count, allowed = middleware._local_incr_and_check("ip", 10.0)

        assert count == 0
        assert allowed is False
        assert "ip" not in middleware.clients

    def test_new_ip_gets_fresh_history(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=3, period=60)

        count, allowed = middleware._local_incr_and_check("new-ip", 500.0)

        assert (count, allowed) == (1, True)
        assert middleware.clients["new-ip"] == deque([500.0])


@pytest.mark.unit
class TestEvictStale:
    def test_drops_stale_ips_but_keeps_active_ones(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=5, period=60)
        middleware.clients["stale-empty"] = deque()
        middleware.clients["stale-old"] = deque([900.0])
        middleware.clients["active"] = deque([970.0])

        middleware._evict_stale(current_time=1000.0)

        assert list(middleware.clients) == ["active"]

    def test_when_still_oversized_drops_oldest_inserted_entries(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=5, period=60)
        for i in range(_MAX_TRACKED_CLIENTS + 50):
            middleware.clients[f"10.0.0.{i}"] = deque([1000.0])

        middleware._evict_stale(current_time=1000.0)

        assert len(middleware.clients) == _MAX_TRACKED_CLIENTS
        assert "10.0.0.0" not in middleware.clients
        assert "10.0.0.49" not in middleware.clients
        assert "10.0.0.50" in middleware.clients

    def test_nothing_to_evict_keeps_everything(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=5, period=60)
        middleware.clients["active"] = deque([999.0])

        middleware._evict_stale(current_time=1000.0)

        assert list(middleware.clients) == ["active"]


@pytest.mark.unit
class TestGetClientIp:
    def test_forwarded_for_first_ip_wins(self):
        request = make_request(headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.9.9.9"})

        assert get_client_ip(request) == "1.2.3.4"

    def test_forwarded_for_single_value_is_trimmed(self):
        request = make_request(headers={"X-Forwarded-For": "  1.2.3.4  "})

        assert get_client_ip(request) == "1.2.3.4"

    def test_real_ip_used_when_no_forwarded_for(self):
        request = make_request(headers={"X-Real-IP": "7.7.7.7"})

        assert get_client_ip(request) == "7.7.7.7"

    def test_forwarded_for_takes_priority_over_real_ip(self):
        request = make_request(headers={"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "7.7.7.7"})

        assert get_client_ip(request) == "1.2.3.4"

    def test_direct_client_without_proxy_headers(self):
        request = make_request(client_host="10.0.0.1")

        assert get_client_ip(request) == "10.0.0.1"

    def test_unknown_when_no_client_info(self):
        request = make_request(client_host=None)

        assert get_client_ip(request) == "unknown"
