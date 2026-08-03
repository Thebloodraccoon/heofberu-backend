from typing import Any

from fastapi import HTTPException
from starlette import status


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