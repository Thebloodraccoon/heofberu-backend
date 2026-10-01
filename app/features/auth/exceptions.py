"""Exceptions for the auth domain."""

from app.core.exceptions import AppError


class AccountAlreadyExistsException(AppError):
    """Raised (400) on a self-registration collision; kept generic to avoid leaking registered emails."""

    status_code = 400

    def __init__(self):
        """Set the duplicate-account message."""

        super().__init__("An account with this email or username already exists.")


class InvalidResetTokenException(AppError):
    """Raised (400) when a password-reset token is invalid, expired, or already used."""

    status_code = 400

    def __init__(self):
        """Set the invalid-reset-token message."""

        super().__init__("The password reset link is invalid or has expired.")
