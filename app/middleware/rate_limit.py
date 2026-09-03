"""
Per-IP rate limiting middleware.

Counters live in Redis (fixed window per ``period``) so the limit is
consistent across all uvicorn workers. When Redis is unavailable the
middleware degrades to a bounded in-memory counter (per-worker, best
effort) instead of failing requests.

The default budget (whatever stage is active) applies to every request.
Endpoint-specific rules — auth, catalog image uploads, and search-heavy
GET lists — may lower (or raise) the effective budget for that request and
count against their *own* Redis bucket, so a burst of login attempts does
not exhaust the caller's general API budget (and vice versa).
"""

from collections import deque
from collections.abc import Callable
import time
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.utils import get_client_ip
from app.settings import settings

# Cap on the in-memory fallback map: with eviction on every request this
# bounds memory even under IP churn (spoofed X-Forwarded-For etc).
_MAX_TRACKED_CLIENTS = 10_000

# Shared bucket for requests that do not match any endpoint-specific rule.
_DEFAULT_BUCKET = "default"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed per-IP rate limiting with a bounded in-memory fallback.

    Args:
        app: The ASGI application.
        calls: Default per-IP budget within the window (unmatched routes).
        period: Fixed window length in seconds.
        skip_paths: Paths exempt from rate limiting.
        rules: Optional endpoint-specific rules (see
            ``MiddlewareConfig.get_route_rules`` for the shape). Each rule
            may set a different ``calls`` budget and counts against its own
            Redis bucket.
        stage: The current deployment stage (``prod``/``staging``/``dev``/``test``).
            Resolves per-route budgets from the rule's stage-specific counts.
    """

    def __init__(
        self,
        app,
        calls: int = 100,
        period: int = 60,
        skip_paths: list[str] | None = None,
        rules: list[dict[str, Any]] | None = None,
        stage: str | None = None,
    ):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.skip_paths = skip_paths or ["/ping", "/health"]
        self.rules = rules or []
        self.stage = stage or getattr(settings, "STAGE", "dev")

        # Fallback only — the primary counter lives in Redis.
        self.clients: dict[str, deque[float]] = {}

    def _resolve_rule(self, request: Request) -> tuple[int, str]:
        """
        Resolve ``(calls, bucket)`` for a request from the route rules.

        The first matching rule wins; rules are ordered most-specific-first
        in ``MiddlewareConfig.get_route_rules``. Unmatched requests fall
        back to the default budget and the shared bucket.
        """

        method = request.method
        path = request.url.path
        query = request.query_params

        for rule in self.rules:
            if rule.get("method") and method != rule["method"]:
                continue

            if rule.get("suffix"):
                if not path.endswith(rule["path"]):
                    continue
            elif not path.startswith(rule["path"]):
                continue

            if rule.get("search") and not query.get("search"):
                continue

            calls = rule.get(self.stage)
            if calls is None:
                calls = rule.get("prod", self.calls)
            return int(calls), rule.get("bucket", _DEFAULT_BUCKET)

        return self.calls, _DEFAULT_BUCKET

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting; over-limit requests get a direct 429 response."""

        if request.url.path in self.skip_paths:
            return await call_next(request)

        client_ip = get_client_ip(request)
        current_time = time.time()
        calls, bucket = self._resolve_rule(request)

        count, allowed = await self._count_and_check(client_ip, bucket, calls, current_time)

        if not allowed:
            # NOTE: return the response directly — an HTTPException raised
            # here would be ABOVE the ExceptionMiddleware and surface as a
            # 500 instead of a 429.
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "type": "rate_limit_exceeded",
                        "message": "Rate limit exceeded",
                        "status_code": 429,
                    }
                },
                headers={
                    "X-RateLimit-Limit": str(calls),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int((current_time // self.period + 1) * self.period)),
                    "Retry-After": str(self.period - int(current_time % self.period)),
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(calls)
        response.headers["X-RateLimit-Remaining"] = str(max(0, calls - count))
        response.headers["X-RateLimit-Reset"] = str(int((current_time // self.period + 1) * self.period))

        return response

    async def _count_and_check(self, client_ip: str, bucket: str, calls: int, current_time: float) -> tuple[int, bool]:
        """
        Increment the client's window counter for ``bucket`` and report
        whether it is still under the (possibly rule-specific) limit.
        Returns ``(count, allowed)``.

        Primary store is Redis (shared across workers); any Redis failure
        falls back to the bounded in-memory counters for this worker.
        """

        try:
            count = await self._redis_incr(client_ip, bucket, current_time)
            return count, count <= calls
        except Exception:
            return self._local_incr_and_check(client_ip, calls, current_time)

    async def _redis_incr(self, client_ip: str, bucket: str, current_time: float) -> int:
        """
        Fixed-window INCR in Redis, with the key expiry set *atomically*.

        ``INCR`` and ``EXPIRE`` are sent together in one pipeline so the
        expiry is attached in the same round-trip that first creates the
        key — a plain ``INCR`` followed by a separate ``EXPIRE`` could drop
        the TTL (and leak the key) if a worker died between the two calls.
        The ``bucket`` is part of the key, so each endpoint family counts
        against an independent budget.
        """

        window = int(current_time // self.period)
        key = f"rate_limit:{client_ip}:{bucket}:{window}"
        async with settings.get_redis() as redis:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.period)
            results = await pipe.execute()
        return int(results[0])

    def _local_incr_and_check(self, client_ip: str, calls: int, current_time: float) -> tuple[int, bool]:
        """Bounded in-memory sliding window (per-worker fallback)."""

        if len(self.clients) > _MAX_TRACKED_CLIENTS:
            self._evict_stale(current_time)

        history = self.clients.setdefault(client_ip, deque())
        cutoff = current_time - self.period
        while history and history[0] < cutoff:
            history.popleft()

        if len(history) >= calls:
            return len(history), False

        history.append(current_time)
        return len(history), True

    def _evict_stale(self, current_time: float) -> None:
        """Drop expired histories; if still oversized, drop oldest-inserted entries."""

        cutoff = current_time - self.period
        stale = [ip for ip, history in self.clients.items() if not history or history[-1] < cutoff]
        for ip in stale:
            del self.clients[ip]

        while len(self.clients) > _MAX_TRACKED_CLIENTS:
            self.clients.pop(next(iter(self.clients)))
