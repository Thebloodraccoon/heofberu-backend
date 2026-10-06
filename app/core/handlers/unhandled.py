"""Catch-all handler for any exception not handled more specifically."""

import logging

from fastapi import Request, status

from app.core.handlers._response import build_error_response, get_request_id

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with a generic 500 (details only in the log)."""

    logger.error(
        "Unhandled Exception: %s - %s - Path: %s - Request ID: %s",
        type(exc).__name__,
        exc,
        request.url.path,
        get_request_id(request),
        exc_info=True,
    )

    return build_error_response(
        request,
        error_type="InternalServerError",
        message="Internal server error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


HANDLERS = [
    (Exception, global_exception_handler),
]
