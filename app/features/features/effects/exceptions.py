"""Feature effect engine exceptions."""

from fastapi import status

from app.core.exceptions import AppError


class InvalidFeatureEffectDataError(AppError):
    """Raised when an effect payload violates the engine's invariant rules."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, message: str = "Invalid feature effect data."):
        """Initialize the error with a human-readable message."""

        super().__init__(message)
