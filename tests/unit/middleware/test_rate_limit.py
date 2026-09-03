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
from app.middleware.rate_limit import _DEFAULT_BUCKET, _MAX_TRACKED_CLIENTS, RateLimitMiddleware
from app.middleware.utils import get_client_ip
from app.settings import settings

AUTH_RULES = [
    {"path": "/api/auth/login", "method": "POST", "bucket": "auth-login", "prod": 3, "staging": 3, "dev": 5},
]


class FakePipeline:
    """Records pipelined commands and returns a fixed result list."""

    def __init__(self, results):
        self.commands = []
        self.results = list(results)

    def incr(self, key):
        self.commands.append(("incr", key))
        return self

    def expire(self, key, ttl):
        self.commands.append(("expire", key, ttl))
        return self

    async def execute(self):
        return self.results


class FakeRedis:
    """Minimal async Redis stand-in returning a fixed ``incr`` result."""

    def __init__(self, incr_result=1):
        self.incr_result = incr_result
        self.pipelines = []

    def pipeline(self):
        pipe = FakePipeline([self.incr_result, True])
        self.pipelines.append(pipe)
        return pipe


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


def make_request(path="/api/things", method="GET", headers=None, query=None, client_host="10.0.0.1"):
    request = SimpleNamespace()
    request.method = method
    request.url = SimpleNamespace(path=path)
    _q = query or {}
    request.query_params = SimpleNamespace(get=lambda k, *a: _q.get(k, *a))
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


def make_middleware(calls=5, period=60, skip_paths=None, now=None, monkeypatch=None, rules=None, stage="dev"):
    if now is not None and monkeypatch is not None:
        monkeypatch.setattr(rate_limit_module, "time", FrozenTime(now))
    return RateLimitMiddleware(
        app=SimpleNamespace(),
        calls=calls,
        period=period,
        skip_paths=skip_paths,
        rules=rules,
        stage=stage,
    )


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
        assert store.pipelines == []

    async def test_default_skip_paths_include_ping_and_health(self, monkeypatch):
        store = FakeRedis()
        make_redis(monkeypatch, store)
        middleware = make_middleware(monkeypatch=monkeypatch)

        for path in ("/ping", "/health"):
            _, seen = await run_dispatch(middleware, make_request(path=path))
            assert len(seen) == 1

        assert store.pipelines == []


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
class TestRouteRules:
    async def test_route_rule_uses_its_own_budget_and_bucket(self, monkeypatch):
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(
            calls=60, period=60, now=1000.0, monkeypatch=monkeypatch, rules=AUTH_RULES, stage="prod"
        )

        response, _ = await run_dispatch(middleware, make_request(path="/api/auth/login", method="POST"))

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["X-RateLimit-Limit"] == "3"
        assert store.pipelines[0].commands[0] == ("incr", "rate_limit:10.0.0.1:auth-login:16")

    async def test_unmatched_route_uses_default_budget_and_bucket(self, monkeypatch):
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(
            calls=60, period=60, now=1000.0, monkeypatch=monkeypatch, rules=AUTH_RULES, stage="prod"
        )

        response, _ = await run_dispatch(middleware, make_request(path="/api/spells"))

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["X-RateLimit-Limit"] == "60"
        assert store.pipelines[0].commands[0] == ("incr", f"rate_limit:10.0.0.1:{_DEFAULT_BUCKET}:16")

    async def test_rule_handler_only_when_method_matches(self, monkeypatch):
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(
            calls=60, period=60, now=1000.0, monkeypatch=monkeypatch, rules=AUTH_RULES, stage="prod"
        )

        # GET to /api/auth/login does NOT match the POST login rule.
        await run_dispatch(middleware, make_request(path="/api/auth/login", method="GET"))

        assert store.pipelines[0].commands[0] == ("incr", f"rate_limit:10.0.0.1:{_DEFAULT_BUCKET}:16")

    async def test_route_rule_blocks_at_its_own_limit(self, monkeypatch):
        store = FakeRedis(incr_result=4)  # exceeds login rule budget of 3
        make_redis(monkeypatch, store)
        middleware = make_middleware(
            calls=60, period=60, now=1000.0, monkeypatch=monkeypatch, rules=AUTH_RULES, stage="prod"
        )

        response, _ = await run_dispatch(middleware, make_request(path="/api/auth/login", method="POST"))

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.headers["X-RateLimit-Limit"] == "3"

    async def test_suffix_rule_matches_image_upload(self, monkeypatch):
        rules = [{"path": "/image", "method": "PUT", "suffix": True, "bucket": "image", "prod": 5, "dev": 20}]
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(
            calls=60, period=60, now=1000.0, monkeypatch=monkeypatch, rules=rules, stage="prod"
        )

        response, _ = await run_dispatch(middleware, make_request(path="/api/races/3/image", method="PUT"))

        assert response.headers["X-RateLimit-Limit"] == "5"
        assert store.pipelines[0].commands[0] == ("incr", "rate_limit:10.0.0.1:image:16")

    async def test_search_rule_only_when_search_param_present(self, monkeypatch):
        rules = [{"path": "/api/spells", "method": "GET", "search": True, "bucket": "search", "prod": 20, "dev": 60}]
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(
            calls=60, period=60, now=1000.0, monkeypatch=monkeypatch, rules=rules, stage="prod"
        )

        # No ?search= -> default budget/bucket.
        await run_dispatch(middleware, make_request(path="/api/spells", method="GET"))
        assert store.pipelines[0].commands[0] == ("incr", f"rate_limit:10.0.0.1:{_DEFAULT_BUCKET}:16")

        # With ?search= -> rule applies.
        await run_dispatch(middleware, make_request(path="/api/spells", method="GET", query={"search": "fire"}))
        assert store.pipelines[1].commands[0] == ("incr", "rate_limit:10.0.0.1:search:16")


@pytest.mark.unit
@pytest.mark.asyncio
class TestCountAndCheckRedis:
    async def test_pipeline_incr_and_expire(self, monkeypatch):
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        count, allowed = await middleware._count_and_check("1.2.3.4", _DEFAULT_BUCKET, 5, 1000.0)

        assert count == 1
        assert allowed is True
        assert store.pipelines[0].commands == [
            ("incr", "rate_limit:1.2.3.4:default:16"),
            ("expire", "rate_limit:1.2.3.4:default:16", 60),
        ]

    async def test_subsequent_incr_with_rule_budget(self, monkeypatch):
        store = FakeRedis(incr_result=7)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        count, allowed = await middleware._count_and_check("1.2.3.4", "auth-login", 3, 1000.0)

        assert count == 7
        assert allowed is False
        assert store.pipelines[0].commands[0] == ("incr", "rate_limit:1.2.3.4:auth-login:16")

    async def test_window_number_is_derived_from_time(self, monkeypatch):
        store = FakeRedis(incr_result=1)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=30, now=61.9, monkeypatch=monkeypatch)

        await middleware._count_and_check("1.2.3.4", _DEFAULT_BUCKET, 5, 61.9)

        assert store.pipelines[0].commands[0] == ("incr", "rate_limit:1.2.3.4:default:2")

    async def test_count_equal_to_limit_is_allowed(self, monkeypatch):
        store = FakeRedis(incr_result=5)
        make_redis(monkeypatch, store)
        middleware = make_middleware(calls=5, period=60, now=1000.0, monkeypatch=monkeypatch)

        _, allowed = await middleware._count_and_check("1.2.3.4", _DEFAULT_BUCKET, 5, 1000.0)

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

        count, allowed = await middleware._count_and_check("1.2.3.4", _DEFAULT_BUCKET, 2, 1000.0)

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

        count, allowed = middleware._local_incr_and_check("1.2.3.4", 5, 1000.0)

        assert count == 1
        assert allowed is True
        assert middleware.clients["1.2.3.4"] == deque([1000.0])

    def test_blocks_at_limit_boundary(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=2, period=60)

        assert middleware._local_incr_and_check("ip", 2, 10.0) == (1, True)
        assert middleware._local_incr_and_check("ip", 2, 11.0) == (2, True)
        assert middleware._local_incr_and_check("ip", 2, 12.0) == (2, False)

    def test_rule_budget_uses_its_own_limit(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=5, period=60)

        assert middleware._local_incr_and_check("ip", 1, 10.0) == (1, True)
        assert middleware._local_incr_and_check("ip", 1, 11.0) == (1, False)

    def test_blocked_requests_do_not_append_timestamps(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=1, period=60)

        assert middleware._local_incr_and_check("ip", 1, 10.0) == (1, True)
        for tick in (11.0, 30.0, 59.9):
            _, allowed = middleware._local_incr_and_check("ip", 1, tick)
            assert allowed is False

        assert list(middleware.clients["ip"]) == [10.0]

    def test_blocked_empty_history_entry_keeps_entry(self):
        """
        With a ``0`` budget every request is blocked; the empty deque stays
        until evicted by ``_evict_stale`` (it is harmless and cheap).
        """
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=0, period=60)

        count, allowed = middleware._local_incr_and_check("ip", 0, 10.0)

        assert count == 0
        assert allowed is False
        assert "ip" in middleware.clients
        assert list(middleware.clients["ip"]) == []

    def test_new_ip_gets_fresh_history(self):
        middleware = RateLimitMiddleware(app=SimpleNamespace(), calls=3, period=60)

        count, allowed = middleware._local_incr_and_check("new-ip", 3, 500.0)

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
    def test_ignores_forwarded_for_header(self):
        request = make_request(headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.9.9.9"})

        assert get_client_ip(request) == "10.0.0.1"

    def test_ignores_real_ip_header(self):
        request = make_request(headers={"X-Real-IP": "7.7.7.7"})

        assert get_client_ip(request) == "10.0.0.1"

    def test_ignores_both_proxy_headers(self):
        request = make_request(headers={"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "7.7.7.7"})

        assert get_client_ip(request) == "10.0.0.1"

    def test_direct_client_without_proxy_headers(self):
        request = make_request(client_host="10.0.0.1")

        assert get_client_ip(request) == "10.0.0.1"

    def test_unknown_when_no_client_info(self):
        request = make_request(client_host=None)

        assert get_client_ip(request) == "unknown"
