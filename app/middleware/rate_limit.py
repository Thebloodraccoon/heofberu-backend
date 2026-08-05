"""Simple in-memory per-IP rate limiting middleware."""

from collections.abc import Callable
import time

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.utils import get_client_ip


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware."""

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
        self.clients: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        if request.url.path in self.skip_paths:
            return await call_next(request)

        client_ip = get_client_ip(request)
        current_time = time.time()

        if client_ip not in self.clients:
            self.clients[client_ip] = []

        self.clients[client_ip] = [
            req_time for req_time in self.clients[client_ip] if current_time - req_time < self.period
        ]

        if len(self.clients[client_ip]) >= self.calls:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": self.calls,
                    "period": self.period,
                    "reset_time": int(current_time + self.period),
                },
            )

        self.clients[client_ip].append(current_time)
        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(self.calls - len(self.clients[client_ip]))
        response.headers["X-RateLimit-Reset"] = str(int(current_time + self.period))

        return response
