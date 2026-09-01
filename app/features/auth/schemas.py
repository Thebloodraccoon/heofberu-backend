"""Request/response schemas for the auth endpoints."""

import re

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.core.exceptions import InvalidEmailException
from app.features.users.exceptions import InvalidPasswordException


class LoginRequest(BaseModel):
    """Login payload: email + password for an existing account."""

    email: str
    password: str

    @field_validator("email")
    def validate_email(cls, email):
        """Reject emails not matching the standard address pattern."""

        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise InvalidEmailException()
        return email


class LoginResponse(BaseModel):
    """Response body for a successful login (access token only)."""

    access_token: str


class LogoutResponse(BaseModel):
    """Response body for a successful logout."""

    detail: str


class RefreshResponse(BaseModel):
    """Response body for a successful token refresh (access token only)."""

    access_token: str


class RegisterRequest(BaseModel):
    """Self-registration payload — always creates a ``PLAYER`` account."""

    username: str
    email: str
    password: str

    @field_validator("email")
    def validate_email(cls, email):
        """Reject emails not matching the standard address pattern."""

        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise InvalidEmailException()
        return email

    @field_validator("username")
    def validate_username(cls, username):
        """Enforce username length and allowed character set."""

        if len(username) < 3 or len(username) > 32:
            raise ValueError("Username must be between 3 and 32 characters long")
        if not re.match(r"^[A-Za-z0-9А-Яа-яЁёІіЇїЄєҐґ_-]+$", username):
            raise ValueError(
                "Username can only contain letters, numbers, underscores, and hyphens"
            )
        return username

    @field_validator("password")
    def validate_password(cls, password):
        """Enforce a minimum password length of 8 characters."""

        if len(password) < 8:
            raise InvalidPasswordException("Password must be at least 8 characters long")
        return password


class RegisterResponse(BaseModel):
    """Response for a successful self-registration — same shape as ``LoginResponse``."""

    access_token: str


class ForgotPasswordRequest(BaseModel):
    """Payload for requesting a password-reset email."""

    email: str

    @field_validator("email")
    def validate_email(cls, email):
        """Reject emails not matching the standard address pattern."""

        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise InvalidEmailException()
        return email


class ForgotPasswordResponse(BaseModel):
    """Neutral response, identical whether or not the account exists, to prevent email enumeration."""

    detail: str


class ResetPasswordRequest(BaseModel):
    """
    Payload for setting a new password: emailed token plus a twice-typed
    new password; ``extra="forbid"``.
    """

    token: str
    new_password: str
    confirm_password: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    def validate_new_password(cls, password):
        """Enforce a minimum password length of 8 characters."""

        if len(password) < 8:
            raise InvalidPasswordException("Password must be at least 8 characters long")
        return password

    @model_validator(mode="after")
    def passwords_match(self):
        """Raise if the two password fields differ."""

        if self.new_password != self.confirm_password:
            raise InvalidPasswordException("Passwords do not match")
        return self


class ResetPasswordResponse(BaseModel):
    """Response for a successful password reset."""

    detail: str
