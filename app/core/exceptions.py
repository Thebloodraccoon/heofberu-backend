"""
Application exceptions and the standardized error response format.

Defines the ``ErrorResponse`` payload shape and ONE exception regime:
every application error is a plain :class:`AppError` subclass carrying its
own ``status_code``/``message`` — services never raise FastAPI's
``HTTPException``. A single generic handler in ``app/core/handlers``
maps any ``AppError`` to the standardized JSON envelope; framework-level
HTTP/Starlette exceptions keep their own handlers.
"""

from datetime import datetime
from typing import Any

from starlette import status


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


class AppError(Exception):
    """
    Base class for every application error (one exception regime).

    Subclasses declare their ``status_code`` (and optionally ``headers``
    or ``details``) and pass a human-readable message to ``super().__init__``.
    The generic ``AppError`` handler turns them into the standardized
    error envelope — feature modules never touch ``fastapi.HTTPException``.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    headers: dict[str, str] | None = None

    def __init__(self, message: str, *, details: Any = None):
        self.message = message
        self.details = details
        super().__init__(message)


class GmAccessException(AppError):
    """Raised (403) when a non-GM user tries to access a GM-only endpoint."""

    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self):
        super().__init__("Only game master has access")


class FoundFatherAccessException(AppError):
    """Raised (403) when a non-found-father user tries an action reserved for the found father."""

    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self):
        super().__init__("Only the found father has access")


class InvalidCredentialsException(AppError):
    """Raised (401) when the provided email or password is incorrect."""

    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self):
        super().__init__("Invalid email or password")


class InvalidTokenException(AppError):
    """Raised (401) when a token is missing, malformed, expired, or of the wrong type."""

    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self):
        super().__init__("Could not validate credentials")
        self.headers = {"WWW-Authenticate": "Bearer"}


class InvalidEmailException(AppError):
    """Raised (400) when a supplied email address fails validation."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str = "Invalid email address"):
        super().__init__(message)


class RecordAlreadyExistsError(Exception):
    """Data Layer Exception: A record with this unique field already exists."""

    def __init__(self, model_name: str, field: str, value: Any):
        self.model_name = model_name
        self.field = field
        self.value = value
        self.message = f"{model_name} with {field} '{value}' already exists."
        super().__init__(self.message)


class RecordNotFoundError(Exception):
    """Data Layer Exception: A record with the given ID does not exist."""

    def __init__(self, model_name: str, model_id: str):
        self.model_name = model_name
        self.id = model_id
        self.message = f"{model_name} with id {model_id} not found."
        super().__init__(self.message)


class RecordIdsInvalidError(Exception):
    """Data Layer Exception: raised when one or more provided record IDs do not correspond to existing records."""

    def __init__(self, model_name: str, ids: list[int]):
        self.model_name = model_name
        self.ids = ids
        self.message = f"Invalid {model_name} id(s): {ids}."
        super().__init__(self.message)


class RecordInUseError(Exception):
    """
    Raised when attempting to delete a record that is still referenced
    elsewhere (e.g. via an ON DELETE RESTRICT foreign key), and therefore
    cannot be removed.

    Mirrors RecordNotFoundError / RecordIdsInvalidError: a plain,
    feature-agnostic exception caught by a single handler in data_layer.py
    and turned into a 409 response, instead of every feature defining its
    own FooInUseException(HTTPException).
    """

    def __init__(self, model_name: str, model_id: int | str, reason: str | None = None):
        self.model_name = model_name
        self.model_id = model_id
        self.reason = reason
        self.message = (
            f"{model_name} with id {model_id} is still in use and cannot be deleted."
            if reason is None
            else f"{model_name} with id {model_id} is still in use and cannot be deleted: {reason}."
        )
        super().__init__(self.message)
