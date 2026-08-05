"""Request/response logging middleware."""

from collections.abc import Callable
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.utils import get_client_ip

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging."""

    def __init__(
        self,
        app,
        log_requests: bool = True,
        log_responses: bool = True,
        skip_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.skip_paths = skip_paths or ["/ping", "/health", "/docs", "/openapi.json"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with comprehensive logging."""
        if request.url.path in self.skip_paths:
            return await call_next(request)

        start_time = time.time()
        request_id = getattr(request.state, "request_id", "unknown")

        if self.log_requests:
            logger.info(
                f"Incoming request: {request.method} {request.url.path} - "
                f"Request ID: {request_id} - "
                f"User-Agent: {request.headers.get('user-agent', 'Unknown')} - "
                f"Client IP: {get_client_ip(request)} - "
                f"Query params: {dict(request.query_params)}"
            )

        try:
            response = await call_next(request)

            if self.log_responses:
                process_time = time.time() - start_time
                logger.info(
                    f"Outgoing response: {response.status_code} - "
                    f"Request ID: {request_id} - "
                    f"Processing time: {process_time:.4f}s - "
                    f"Content-Length: {response.headers.get('content-length', 'Unknown')} - "
                    f"Content-Type: {response.headers.get('content-type', 'Unknown')}"
                )

            return response

        except Exception as e:
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
