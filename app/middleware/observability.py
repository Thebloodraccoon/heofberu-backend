"""
Merged request-id / logging / timing middleware.

Was three separate ``BaseHTTPMiddleware`` layers (``RequestIDMiddleware``,
``LoggingMiddleware``, ``TimingMiddleware``), each paying Starlette's
per-layer ``BaseHTTPMiddleware`` overhead (a fresh ``anyio`` task group +
memory-object-stream per request to bridge ``call_next`` back to ``send``)
on top of each other for what is really one concern: per-request
instrumentation. Merged into a single ``dispatch`` so that overhead is paid
once instead of three times, with identical externally-observable behavior
(same headers, same log lines, same skip-path semantics).
"""

from collections.abc import Callable
import logging
import re
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.utils import get_client_ip

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Request ID tagging + request/response logging + processing-time header, in one pass."""

    def __init__(
        self,
        app,
        request_id_header: str = "X-Request-ID",
        log_requests: bool = True,
        log_responses: bool = True,
        log_skip_paths: list[str] | None = None,
        log_slow_requests: bool = True,
        slow_threshold: float = 1.0,
    ):
        super().__init__(app)
        self.request_id_header = request_id_header
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.log_skip_paths = log_skip_paths or ["/ping", "/health", "/docs", "/openapi.json", "/redoc"]
        self.log_slow_requests = log_slow_requests
        self.slow_threshold = slow_threshold

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Tag the request with an id, time it, log it (unless skipped), and stamp the response headers."""

        raw = request.headers.get(self.request_id_header, "")
        request_id = raw if _UUID_RE.match(raw) else str(uuid.uuid4())
        request.state.request_id = request_id

        skip_logging = request.url.path in self.log_skip_paths

        if self.log_requests and not skip_logging:
            logger.info(
                f"Incoming request: {request.method} {request.url.path} - "
                f"Request ID: {request_id} - "
                f"User-Agent: {request.headers.get('user-agent', 'Unknown')} - "
                f"Client IP: {get_client_ip(request)} - "
                f"Query params: {dict(request.query_params)}"
            )

        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as e:
            if not skip_logging:
                process_time = time.time() - start_time
                logger.error(
                    f"Request failed: {str(e)} - "
                    f"Request ID: {request_id} - "
                    f"Processing time: {process_time:.4f}s - "
                    f"Path: {request.url.path} - "
                    f"Method: {request.method} - "
                    f"Client IP: {get_client_ip(request)}",
                    exc_info=True,
                )
            raise

        process_time = time.time() - start_time

        response.headers[self.request_id_header] = request_id
        response.headers["X-Process-Time"] = str(round(process_time, 4))

        if self.log_responses and not skip_logging:
            logger.info(
                f"Outgoing response: {response.status_code} - "
                f"Request ID: {request_id} - "
                f"Processing time: {process_time:.4f}s - "
                f"Content-Length: {response.headers.get('content-length',  'Unknown')} - "
                f"Content-Type: {response.headers.get('content-type', 'Unknown')}"
            )

        if self.log_slow_requests and process_time > self.slow_threshold:
            logger.warning(
                f"Slow request detected: {request.method} {request.url.path} - "
                f"Processing time: {process_time:.4f}s - "
                f"Response status: {response.status_code}"
            )

        return response
