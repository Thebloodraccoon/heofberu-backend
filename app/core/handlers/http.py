"""Exception handlers for HTTP-layer exceptions (FastAPI and Starlette)."""

import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import ErrorResponse

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        f"HTTP Exception: {exc.status_code} - {exc.detail} - Path: {request.url.path} - Request ID: {request_id}"
    )

    error_response = ErrorResponse(
        error_type="HTTPException",
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.to_dict(),
        headers=getattr(exc, "headers", None),
    )


async def starlette_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle Starlette HTTP exceptions."""
    request_id = getattr(request.state, "request_id", None)

    error_response = ErrorResponse(
        error_type="StarletteHTTPException",
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id,
    )

    return JSONResponse(status_code=exc.status_code, content=error_response.to_dict())


HANDLERS = [
    (HTTPException, http_exception_handler),
    (StarletteHTTPException, starlette_exception_handler),
]
