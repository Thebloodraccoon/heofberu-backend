"""Shared builder for the standardized error envelope response."""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import ErrorResponse


def get_request_id(request: Request) -> str | None:
    """The request id stamped by ``ObservabilityMiddleware`` (``None`` outside the full stack)."""

    return getattr(request.state, "request_id", None)


def build_error_response(
    request: Request,
    *,
    error_type: str,
    message: str,
    status_code: int,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Return the ``{"error": {...}}`` JSON envelope with the request id attached."""

    envelope = ErrorResponse(
        error_type=error_type,
        message=message,
        status_code=status_code,
        details=details,
        request_id=get_request_id(request),
    )

    return JSONResponse(status_code=status_code, content=envelope.to_dict(), headers=headers)
