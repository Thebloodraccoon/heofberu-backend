"""
Exception handlers for request/Pydantic validation failures (422).

The error payload carries only the field path, message and error type. The
submitted ``input`` is never echoed back or logged: it may be a password or
another secret.
"""

import logging
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.handlers._response import build_error_response, get_request_id

logger = logging.getLogger(__name__)


def _summarize(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Reduce raw Pydantic errors to ``field``/``message``/``type`` (no ``input``, no ``ctx``)."""

    return [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in errors
    ]


def _respond(request: Request, errors: list[dict[str, Any]], error_type: str):
    summary = _summarize(errors)

    logger.warning(
        "Validation Error: fields=%s - Path: %s - Request ID: %s",
        [item["field"] for item in summary],
        request.url.path,
        get_request_id(request),
    )

    return build_error_response(
        request,
        error_type=error_type,
        message="Validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"validation_errors": summary},
    )


async def request_validation_handler(request: Request, exc: RequestValidationError):
    """Handle body/query/path validation errors raised by FastAPI."""

    return _respond(request, list(exc.errors()), "RequestValidationError")


async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic ``ValidationError`` raised inside services (e.g. manual ``Schema(**data)``)."""

    return _respond(request, exc.errors(), "ValidationError")


HANDLERS = [
    (RequestValidationError, request_validation_handler),
    (ValidationError, validation_exception_handler),
]
