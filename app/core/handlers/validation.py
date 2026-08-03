import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.exceptions import ErrorResponse

logger = logging.getLogger(__name__)


async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors."""

    request_id = getattr(request.state, "request_id", None)

    logger.warning(f"Validation Error: {exc.errors()} - Path: {request.url.path} - Request ID: {request_id}")

    validation_errors = [
        {
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
            "input": error.get("input"),
        }
        for error in exc.errors()
    ]

    error_response = ErrorResponse(
        error_type="ValidationError",
        message="Validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"validation_errors": validation_errors},
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.to_dict(),
    )


HANDLERS = [
    (ValidationError, validation_exception_handler),
]
