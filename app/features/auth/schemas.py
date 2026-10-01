"""Request/response schemas for the auth endpoints."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.features.users.exceptions import InvalidPasswordException
from app.features.users.validators import Email, NewPassword, Username

# Login accepts any previously valid password but still bounds the work done per request.
LOGIN_PASSWORD_MAX_LENGTH = 1024
LoginPassword = Annotated[str, StringConstraints(max_length=LOGIN_PASSWORD_MAX_LENGTH)]


class LoginRequest(BaseModel):
    """Login payload: email + password for an existing account."""

    email: Email
    password: LoginPassword


class RegisterRequest(BaseModel):
    """Self-registration payload — always creates a ``PLAYER`` account."""

    username: Username
    email: Email
    password: NewPassword


class ForgotPasswordRequest(BaseModel):
    """Payload for requesting a password-reset email."""

    email: Email


class ResetPasswordRequest(BaseModel):
    """
    Payload for setting a new password: emailed token plus a twice-typed
    new password; ``extra="forbid"``.
    """

    token: str
    new_password: NewPassword
    confirm_password: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def passwords_match(self):
        """Raise if the two password fields differ."""

        if self.new_password != self.confirm_password:
            raise InvalidPasswordException("Passwords do not match")
        return self


class AccessTokenResponse(BaseModel):
    """Response body carrying a freshly issued access token (the refresh token travels in a cookie)."""

    access_token: str


class LoginResponse(AccessTokenResponse):
    """Response body for a successful login."""


class RegisterResponse(AccessTokenResponse):
    """Response for a successful self-registration."""


class RefreshResponse(AccessTokenResponse):
    """Response body for a successful token refresh."""


class LogoutResponse(BaseModel):
    """Response body for a successful logout."""

    detail: str


class ForgotPasswordResponse(BaseModel):
    """Neutral response, identical whether or not the account exists, to prevent email enumeration."""

    detail: str


class ResetPasswordResponse(BaseModel):
    """Response for a successful password reset."""

    detail: str
