"""User-specific application exceptions."""

from app.core.exceptions import AppError


class UserNotFoundException(AppError):
    """Raised (404) when a user cannot be found; the message never echoes the looked-up email."""

    status_code = 404

    def __init__(self):
        """Set the generic not-found message."""

        super().__init__("User is not found")


class InvalidPasswordException(AppError):
    """Raised (400) when a supplied password fails the strength rules."""

    status_code = 400

    def __init__(self, message: str = "Invalid password"):
        """Set the invalid-password message."""

        super().__init__(message)


class DefaultUserProtectedException(AppError):
    """Raised (403) when someone tries to update/delete the seeded admin."""

    status_code = 403

    def __init__(self, message: str = "The default admin user cannot be updated or deleted."):
        """Set the default-user-protected message."""

        super().__init__(message)


class SelfDeletionException(AppError):
    """Raised (403) when a user tries to delete their own account."""

    status_code = 403

    def __init__(self, message: str = "You cannot delete your own account."):
        """Set the self-deletion message."""

        super().__init__(message)
