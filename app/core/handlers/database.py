"""
Exception handler for SQLAlchemy errors.

``IntegrityError`` becomes a 409 for a unique violation and a 400 otherwise, with a message derived from the
PostgreSQL SQLSTATE (unique / foreign key / not-null / check); pool
exhaustion becomes a 503; any other database error a generic 500.
Statements, parameters and constraint detail are logged at most by
constraint name and never returned to the client.
"""

import logging

from fastapi import Request, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.db_errors import (
    CHECK_VIOLATION,
    FOREIGN_KEY_VIOLATION,
    NOT_NULL_VIOLATION,
    UNIQUE_VIOLATION,
    constraint_name,
    sqlstate,
)
from app.core.handlers._response import build_error_response, get_request_id

logger = logging.getLogger(__name__)

_INTEGRITY_MESSAGES = {
    UNIQUE_VIOLATION: "Record with this data already exists",
    FOREIGN_KEY_VIOLATION: "Referenced record does not exist",
    NOT_NULL_VIOLATION: "Required field cannot be empty",
    CHECK_VIOLATION: "Value violates a database constraint",
}


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle SQLAlchemy database errors without leaking SQL or data."""

    request_id = get_request_id(request)

    if isinstance(exc, IntegrityError):
        state = sqlstate(exc)
        logger.warning(
            "Integrity error: sqlstate=%s constraint=%s - Path: %s - Request ID: %s",
            state,
            constraint_name(exc),
            request.url.path,
            request_id,
        )
        message = _INTEGRITY_MESSAGES.get(state or "", "Database integrity constraint violation")
        status_code = status.HTTP_409_CONFLICT if state == UNIQUE_VIOLATION else status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, PoolTimeoutError):
        logger.error("Database pool exhausted - Path: %s - Request ID: %s", request.url.path, request_id)
        message = "Service temporarily unavailable"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        logger.error(
            "Database error: %s sqlstate=%s - Path: %s - Request ID: %s",
            type(exc).__name__,
            sqlstate(exc),
            request.url.path,
            request_id,
            exc_info=True,
        )
        message = "Database operation failed"
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    return build_error_response(request, error_type="DatabaseError", message=message, status_code=status_code)


HANDLERS = [
    (SQLAlchemyError, sqlalchemy_exception_handler),
]
