from fastapi import HTTPException, status


class UserNotFoundException(HTTPException):
    def __init__(self, user_id: int | None = None, email: str | None = None):
        detail = "404 User is not found"

        if user_id:
            detail = f"User with ID {user_id} is not found."

        if email:
            detail = f"User with email {email} is not found."

        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class InvalidPasswordException(HTTPException):
    def __init__(self, message: str = "Invalid password"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


class DefaultUserProtectedException(HTTPException):
    def __init__(self, message: str = "The default admin user cannot be updated or deleted."):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )


class SelfDeletionException(HTTPException):
    def __init__(self, message: str = "You cannot delete your own account."):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )
