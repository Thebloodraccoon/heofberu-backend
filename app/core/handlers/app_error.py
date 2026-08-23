"""
Exception handler for the unified ``AppError`` regime.

Every application error (auth, data layer, feature rules) is an
``AppError`` subclass; this one handler turns any of them into the
standardized error envelope. Feature modules therefore never raise or
catch ``fastapi.HTTPException``.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError, ErrorResponse

logger = logging.getLogger(__name__)


async def app_error_handler(request: Request, exc: AppError):
    """Handle any ``AppError`` (and subclass) with the standardized envelope."""

    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        f"App Error: {exc.status_code} - {exc.message} - Path: {request.url.path} - Request ID: {request_id}"
    )

    error_response = ErrorResponse(
        error_type=type(exc).__name__,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.to_dict(),
        headers=exc.headers,
    )


HANDLERS = [
    # Registered before the framework handlers so AppError subclasses are
    # matched by their own handler, not the generic HTTPException one.
    (AppError, app_error_handler),
]
