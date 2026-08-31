"""Exceptions for the auth domain."""

from app.core.exceptions import AppError


class AccountAlreadyExistsException(AppError):
    """
    Raised (400) when a self-registration collides with an existing
    account. Deliberately generic — the raw ``RecordAlreadyExistsError``
    echoes the offending email, which would let anyone confirm whether an
    address is already registered.
    """

    status_code = 400

    def __init__(self):
        super().__init__("An account with this email or username already exists.")


class InvalidResetTokenException(AppError):
    """
    Raised (400) when a password-reset token is missing, malformed,
    expired, of the wrong type, or has already been used.

    Deliberately a 400 rather than a 401: the bearer isn't authenticating,
    they're redeeming a one-time emailed link.
    """

    status_code = 400

    def __init__(self):
        super().__init__("The password reset link is invalid or has expired.")
