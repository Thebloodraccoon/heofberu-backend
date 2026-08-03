import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exceptions import ErrorResponse

logger = logging.getLogger(__name__)


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


HANDLERS = [
    (SQLAlchemyError, sqlalchemy_exception_handler),
]
