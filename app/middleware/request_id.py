"""Middleware that tags every request and response with a unique request ID."""

from collections.abc import Callable
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware for adding unique request IDs."""

    def __init__(self, app, header_name: str = "X-Request-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add request ID."""

        request_id = request.headers.get(self.header_name, str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[self.header_name] = request_id

        return response
