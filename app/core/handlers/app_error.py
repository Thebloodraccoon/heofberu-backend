"""
Exception handler for the unified ``AppError`` regime.

Every application error (auth, data layer, feature rules) is an
``AppError`` subclass; this one handler turns any of them into the
standardized error envelope. Feature modules therefore never raise or
catch ``fastapi.HTTPException``.
"""

import logging

from fastapi import Request

from app.core.exceptions import AppError
from app.core.handlers._response import build_error_response, get_request_id

logger = logging.getLogger(__name__)


async def app_error_handler(request: Request, exc: AppError):
    """Handle any ``AppError`` (and subclass) with the standardized envelope."""

    logger.warning(
        "App Error: %s - %s - Path: %s - Request ID: %s",
        exc.status_code,
        exc.message,
        request.url.path,
        get_request_id(request),
    )

    return build_error_response(
        request,
        error_type=type(exc).__name__,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        headers=exc.headers,
    )


HANDLERS = [
    # Registered before the framework handlers so AppError subclasses are
    # matched by their own handler, not the generic HTTPException one.
    (AppError, app_error_handler),
]
