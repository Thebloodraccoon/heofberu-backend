"""User-specific application exceptions."""

from app.core.exceptions import AppError


class UserNotFoundException(AppError):
    """Raised (404) when a user cannot be found by email/ID."""

    status_code = 404

    def __init__(self, email: str | None = None):
        detail = "404 User is not found"

        if email:
            detail = f"User with email {email} is not found."

        super().__init__(detail)


class InvalidPasswordException(AppError):
    """Raised (400) when a supplied password fails the strength rules."""

    status_code = 400

    def __init__(self, message: str = "Invalid password"):
        super().__init__(message)


class DefaultUserProtectedException(AppError):
    """Raised (403) when someone tries to update/delete the seeded admin."""

    status_code = 403

    def __init__(self, message: str = "The default admin user cannot be updated or deleted."):
        super().__init__(message)


class SelfDeletionException(AppError):
    """Raised (403) when a user tries to delete their own account."""

    status_code = 403

    def __init__(self, message: str = "You cannot delete your own account."):
        super().__init__(message)
