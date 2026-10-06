"""Exception handler for HTTP-layer exceptions (FastAPI's ``HTTPException`` subclasses Starlette's)."""

import logging

from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.handlers._response import build_error_response, get_request_id

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions, keeping their headers (``Allow``, ``WWW-Authenticate``, ...)."""

    logger.warning(
        "HTTP Exception: %s - %s - Path: %s - Request ID: %s",
        exc.status_code,
        exc.detail,
        request.url.path,
        get_request_id(request),
    )

    return build_error_response(
        request,
        error_type=type(exc).__name__,
        message=str(exc.detail),
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


HANDLERS = [
    (StarletteHTTPException, http_exception_handler),
]
