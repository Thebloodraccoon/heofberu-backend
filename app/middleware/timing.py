"""Middleware that measures and reports request processing time."""

from collections.abc import Callable
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware for measuring request processing time."""

    def __init__(self, app, log_slow_requests: bool = True, slow_threshold: float = 1.0):
        super().__init__(app)
        self.log_slow_requests = log_slow_requests
        self.slow_threshold = slow_threshold

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Measure processing time, set the ``X-Process-Time`` header, and log slow requests."""

        start_time = time.time()

        response = await call_next(request)
        process_time = time.time() - start_time

        response.headers["X-Process-Time"] = str(round(process_time, 4))
        if self.log_slow_requests and process_time > self.slow_threshold:
            logger.warning(
                f"Slow request detected: {request.method} {request.url.path} - "
                f"Processing time: {process_time:.4f}s - "
                f"Response status: {response.status_code}"
            )

        return response
