"""
Per-IP rate limiting middleware.

Counters live in Redis (fixed window per ``period``) so the limit is
consistent across all uvicorn workers. When Redis is unavailable the
middleware degrades to a bounded in-memory counter (per-worker, best
effort) instead of failing requests.
"""

from collections import deque
from collections.abc import Callable
import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.utils import get_client_ip
from app.settings import settings

# Cap on the in-memory fallback map: with eviction on every request this
# bounds memory even under IP churn (spoofed X-Forwarded-For etc).
_MAX_TRACKED_CLIENTS = 10_000


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed per-IP rate limiting with a bounded in-memory fallback."""

    def __init__(
        self,
        app,
        calls: int = 100,
        period: int = 60,
        skip_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.skip_paths = skip_paths or ["/ping", "/health"]
        # Fallback only — the primary counter lives in Redis.
        self.clients: dict[str, deque[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting; over-limit requests get a direct 429 response."""

        if request.url.path in self.skip_paths:
            return await call_next(request)

        client_ip = get_client_ip(request)
        current_time = time.time()

        count, allowed = await self._count_and_check(client_ip, current_time)

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
                    "X-RateLimit-Limit": str(self.calls),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int((current_time // self.period + 1) * self.period)),
                    "Retry-After": str(self.period - int(current_time % self.period)),
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.calls - count))
        response.headers["X-RateLimit-Reset"] = str(int((current_time // self.period + 1) * self.period))

        return response

    async def _count_and_check(self, client_ip: str, current_time: float) -> tuple[int, bool]:
        """
        Increment the client's window counter and report whether it is still
        under the limit. Returns ``(count, allowed)``.

        Primary store is Redis (shared across workers); any Redis failure
        falls back to the bounded in-memory counters for this worker.
        """

        try:
            count = await self._redis_incr(client_ip, current_time)
            return count, count <= self.calls
        except Exception:
            return self._local_incr_and_check(client_ip, current_time)

    async def _redis_incr(self, client_ip: str, current_time: float) -> int:
        """Fixed-window INCR in Redis; the key expires one period after creation."""

        window = int(current_time // self.period)
        key = f"rate_limit:{client_ip}:{window}"
        async with settings.get_redis() as redis:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, self.period * 2)
        return int(count)

    def _local_incr_and_check(self, client_ip: str, current_time: float) -> tuple[int, bool]:
        """Bounded in-memory sliding window (per-worker fallback)."""

        if len(self.clients) > _MAX_TRACKED_CLIENTS:
            self._evict_stale(current_time)

        history = self.clients.setdefault(client_ip, deque())
        cutoff = current_time - self.period
        while history and history[0] < cutoff:
            history.popleft()

        if len(history) >= self.calls:
            # Refresh eviction pressure bookkeeping without appending.
            if not history:
                del self.clients[client_ip]
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
