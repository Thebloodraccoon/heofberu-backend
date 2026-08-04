from datetime import datetime
from typing import Any

from fastapi import HTTPException
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


class GmAccessException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only game master has access",
        )


class InvalidCredentialsException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )


class InvalidTokenException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            detail="Could not validate credentials",
        )


class InvalidEmailException(HTTPException):
    def __init__(self, message: str = "Invalid email address"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


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
