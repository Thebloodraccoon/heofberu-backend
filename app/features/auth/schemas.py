import re

from pydantic import BaseModel, field_validator

from app.core.exceptions import InvalidEmailException
from app.features.users.exceptions import InvalidPasswordException


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    def validate_email(cls, email):
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise InvalidEmailException()
        return email


class LoginResponse(BaseModel):
    access_token: str


class LogoutResponse(BaseModel):
    detail: str


class RefreshResponse(BaseModel):
    access_token: str


class RegisterRequest(BaseModel):
    """
    Public self-service registration payload.

    Deliberately has no ``role`` field — unlike ``UserCreate`` (used by
    the GM-only ``POST /users/`` endpoint), a self-registered account is
    always created as ``UserRole.PLAYER`` by ``AuthService.register``,
    never chosen by the caller. Validation mirrors ``UserBase``/
    ``UserCreate`` in ``app.features.users.schemas`` (same username/email/
    password rules) so a registered account satisfies the same
    constraints as a GM-created one, without importing ``UserCreate``
    itself and inheriting a ``role`` field this endpoint must not accept.
    """

    username: str
    email: str
    password: str

    @field_validator("email")
    def validate_email(cls, email):
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise InvalidEmailException()
        return email

    @field_validator("username")
    def validate_username(cls, username):
        if len(username) < 3 or len(username) > 32:
            raise ValueError("Username must be between 3 and 32 characters long")
        if not re.match(r"^[a-zA-Z0-9_-]+$", username):
            raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
        return username

    @field_validator("password")
    def validate_password(cls, password):
        if len(password) < 8:
            raise InvalidPasswordException("Password must be at least 8 characters long")
        return password


class RegisterResponse(BaseModel):
    """
    Response for a successful self-registration.

    Same shape as ``LoginResponse`` — registration logs the new user in
    immediately (an ``access_token`` plus the refresh cookie set on the
    response), rather than requiring a separate follow-up login call. A
    distinct class (rather than reusing ``LoginResponse``) exists so the
    two endpoints' response models can diverge later without one
    surprising the other.
    """

    access_token: str
