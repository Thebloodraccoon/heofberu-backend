from datetime import datetime
import logging
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import RecordAlreadyExistsError

logger = logging.getLogger(__name__)


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat() + "Z"


class ErrorResponse:
    """Standardized error response format."""

    def __init__(
        self,
        error_type: str,
        message: str,
        status_code: int,
        details: Any = None,
        request_id: str | None = None,
    ):
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.details = details
        self.request_id = request_id

    def to_dict(self) -> dict[str, Any]:
        """Convert error response to dictionary format."""
        response = {
            "error": {
                "type": self.error_type,
                "message": self.message,
                "status_code": self.status_code,
                "timestamp": get_timestamp(),
            }
        }

        if self.details:
            response["error"]["details"] = self.details

        if self.request_id:
            response["error"]["request_id"] = self.request_id

        return response


def setup_error_handlers(app):
    """Setting a global error handler for Fastapi application."""

    @app.exception_handler(HTTPException)
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

    @app.exception_handler(StarletteHTTPException)
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

    @app.exception_handler(ValidationError)
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

    @app.exception_handler(RecordAlreadyExistsError)
    async def record_already_exists_handler(request: Request, exc: RecordAlreadyExistsError):
        """Handle uniqueness violations raised by BaseRepository._check_uniqueness."""

        request_id = getattr(request.state, "request_id", None)

        logger.warning(f"Uniqueness violation: {exc.message} - Path: {request.url.path} - Request ID: {request_id}")

        error_response = ErrorResponse(
            error_type="RecordAlreadyExistsError",
            message=exc.message,
            status_code=status.HTTP_400_BAD_REQUEST,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response.to_dict(),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        """Handle SQLAlchemy database errors."""
        request_id = getattr(request.state, "request_id", None)

        logger.error(f"Database Error: {str(exc)} - Path: {request.url.path} - Request ID: {request_id}")

        if isinstance(exc, IntegrityError):
            error_detail = "Database integrity constraint violation"
            status_code = status.HTTP_400_BAD_REQUEST

            error_str = str(exc.orig) if hasattr(exc, "orig") else str(exc)
            if "UNIQUE" in error_str.upper():
                error_detail = "Record with this data already exists"
            elif "FOREIGN KEY" in error_str.upper():
                error_detail = "Referenced record does not exist"
            elif "NOT NULL" in error_str.upper():
                error_detail = "Required field cannot be empty"
        else:
            error_detail = "Database operation failed"
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        error_response = ErrorResponse(
            error_type="DatabaseError",
            message=error_detail,
            status_code=status_code,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=status_code,
            content=error_response.to_dict(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle all unhandled exceptions."""
        request_id = getattr(request.state, "request_id", None)

        logger.error(
            f"Unhandled Exception: {type(exc).__name__} - {str(exc)} - "
            f"Path: {request.url.path} - Request ID: {request_id}",
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
