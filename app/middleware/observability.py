"""
Request-id tagging, request/response logging and the processing-time header in
one ``BaseHTTPMiddleware`` layer (one layer instead of three avoids paying
Starlette's per-layer task-group overhead repeatedly).
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

DEFAULT_LOG_SKIP_PATHS = ["/api/ping", "/api/health", "/docs", "/openapi.json", "/redoc"]

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def _sanitize(value: str) -> str:
    """Strip CR/LF so a client-controlled header cannot forge log lines."""

    return value.replace("\r", " ").replace("\n", " ")


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
        self.log_skip_paths = log_skip_paths if log_skip_paths is not None else DEFAULT_LOG_SKIP_PATHS
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
                "Incoming request: %s %s - Request ID: %s - User-Agent: %s - Client IP: %s - Query params: %s",
                request.method,
                request.url.path,
                request_id,
                _sanitize(request.headers.get("user-agent", "Unknown")),
                get_client_ip(request),
                dict(request.query_params),
            )

        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as e:
            if not skip_logging:
                process_time = time.time() - start_time
                logger.error(
                    "Request failed: %s - Request ID: %s - Processing time: %.4fs - Path: %s - Method: %s - Client IP: %s",
                    e,
                    request_id,
                    process_time,
                    request.url.path,
                    request.method,
                    get_client_ip(request),
                    exc_info=True,
                )
            raise

        process_time = time.time() - start_time

        response.headers[self.request_id_header] = request_id
        response.headers["X-Process-Time"] = str(round(process_time, 4))

        if self.log_responses and not skip_logging:
            logger.info(
                "Outgoing response: %s - Request ID: %s - Processing time: %.4fs - Content-Length: %s - Content-Type: %s",
                response.status_code,
                request_id,
                process_time,
                response.headers.get("content-length", "Unknown"),
                response.headers.get("content-type", "Unknown"),
            )

        if self.log_slow_requests and process_time > self.slow_threshold:
            logger.warning(
                "Slow request detected: %s %s - Processing time: %.4fs - Response status: %s",
                request.method,
                request.url.path,
                process_time,
                response.status_code,
            )

        return response
