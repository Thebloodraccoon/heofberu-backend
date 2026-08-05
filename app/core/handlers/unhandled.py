"""Catch-all handler for any exception not handled more specifically."""

import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import ErrorResponse

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        f"Unhandled Exception: {type(exc).__name__} - {str(exc)} - Path: {request.url.path} - Request ID: {request_id}",
        exc_info=True,
    )

    error_response = ErrorResponse(
        error_type="InternalServerError",
        message="Internal server error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.to_dict(),
    )


HANDLERS = [
    (Exception, global_exception_handler),
]
