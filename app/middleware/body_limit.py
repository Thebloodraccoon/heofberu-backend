"""
Request body-size guard middleware.

Rejects requests whose declared body size exceeds
``settings.REQUEST_BODY_MAX_BYTES`` with a 413 before the body is read.
This guards the JSON endpoints; binary uploads (catalog images) additionally
enforce ``IMAGE_MAX_BYTES`` on the actual bytes in the storage service, and
the precise byte count is ultimately enforced at the reverse proxy
(``client_max_body_size``). Only the synced ``Content-Length`` is checked
here — a chunked body with no ``Content-Length`` cannot be pre-empted, but
the per-field/bytes checks downstream still cap them.
"""

from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware

from app.settings import settings


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose ``Content-Length`` exceeds the stage limit."""

    def __init__(self, app, max_bytes: int | None = None):
        super().__init__(app)
        self.max_bytes = max_bytes if max_bytes is not None else settings.REQUEST_BODY_MAX_BYTES

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check ``Content-Length`` and return 413 when the body is too large."""

        content_length = request.headers.get("Content-Length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "error": {
                        "type": "payload_too_large",
                        "message": f"Request body exceeds the {self.max_bytes // (1024 * 1024)} MB limit.",
                        "status_code": 413,
                    }
                },
            )

        return await call_next(request)
