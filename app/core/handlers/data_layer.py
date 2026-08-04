import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import ErrorResponse, RecordAlreadyExistsError, RecordIdsInvalidError, RecordNotFoundError

logger = logging.getLogger(__name__)


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


async def record_not_found_handler(request: Request, exc: RecordNotFoundError):
    """Handle not found error raised by BaseService."""

    request_id = getattr(request.state, "request_id", None)

    logger.warning(f"Not found error: {exc.message} - Path: {request.url.path} - Request ID: {request_id}")

    error_response = ErrorResponse(
        error_type="RecordNotFoundError",
        message=exc.message,
        status_code=status.HTTP_404_NOT_FOUND,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=error_response.to_dict(),
    )


async def record_ids_invalid_handler(request: Request, exc: RecordIdsInvalidError):
    """Handle invalid ids raised by BaseService."""

    request_id = getattr(request.state, "request_id", None)

    logger.warning(f"Not found error: {exc.message} - Path: {request.url.path} - Request ID: {request_id}")

    error_response = ErrorResponse(
        error_type="RecordIdsInvalidError",
        message=exc.message,
        status_code=status.HTTP_400_BAD_REQUEST,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=error_response.to_dict(),
    )


HANDLERS = [
    (RecordAlreadyExistsError, record_already_exists_handler),
    (RecordNotFoundError, record_not_found_handler),
    (RecordIdsInvalidError, record_ids_invalid_handler),
]
