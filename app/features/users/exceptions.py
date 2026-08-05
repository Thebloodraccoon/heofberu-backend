"""User-specific HTTP exceptions."""

from fastapi import HTTPException, status


class UserNotFoundException(HTTPException):
    """Raised (404) when a user cannot be found by email/ID."""

    def __init__(self, email: str | None = None):
        detail = "404 User is not found"

        if email:
            detail = f"User with email {email} is not found."

        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class InvalidPasswordException(HTTPException):
    """Raised (400) when a supplied password fails the strength rules."""

    def __init__(self, message: str = "Invalid password"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


class DefaultUserProtectedException(HTTPException):
    """Raised (403) when someone tries to update/delete the seeded admin."""

    def __init__(self, message: str = "The default admin user cannot be updated or deleted."):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )


class SelfDeletionException(HTTPException):
    """Raised (403) when a user tries to delete their own account."""

    def __init__(self, message: str = "You cannot delete your own account."):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )
