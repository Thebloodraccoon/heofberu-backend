"""Request/response schemas for user management."""

from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.constants import UserRole
from app.core.exceptions import InvalidEmailException
from app.features.users.exceptions import InvalidPasswordException


class ProfileFields(BaseModel):
    """Validators shared by every schema carrying editable profile fields."""

    @field_validator("email", check_fields=False)
    def validate_email(cls, email):
        """Reject emails not matching the standard address pattern (when provided)."""

        if email is not None and not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise InvalidEmailException()
        return email

    @field_validator("username", check_fields=False)
    def validate_username(cls, username):
        """Enforce username length and allowed character set (when provided)."""

        if username is not None:
            if len(username) < 3 or len(username) > 32:
                raise ValueError("Username must be between 3 and 32 characters long")
            if not re.match(r"^[A-Za-z0-9А-Яа-яЁёІіЇїЄєҐґ_-]+$", username):
                raise ValueError(
                    "Username can only contain letters, numbers, underscores, and hyphens"
                )
        return username


class UserBase(ProfileFields):
    """Base user fields shared by create and response schemas."""

    username: str
    role: UserRole = UserRole.PLAYER
    email: str

    bio: str | None = None
    phone: str | None = None
    discord: str | None = None
    telegram: str | None = None


class UserCreate(UserBase):
    """Payload for creating a user, adding the plaintext ``password``."""

    password: str

    @field_validator("password")
    def validate_password(cls, password):
        """Enforce a minimum password length of 8 characters."""

        if len(password) < 8:
            raise InvalidPasswordException("Password must be at least 8 characters long")
        return password


class UserUpdate(ProfileFields):
    """Partial-update payload: at least one of the optional fields must be set."""

    username: str | None = None
    email: str | None = None
    role: UserRole | None = None

    bio: str | None = None
    phone: str | None = None
    discord: str | None = None
    telegram: str | None = None

    @model_validator(mode="before")
    def validate_data(cls, values):
        """Reject a payload in which every updatable field is ``None``."""

        if not any(key for key in values if key != "id" and values[key] is not None):
            raise ValueError("At least one updatable field must be provided.")
        return values


class UserProfileUpdate(ProfileFields):
    """Self-service payload for the personal cabinet — no ``role`` field."""

    username: str | None = None
    email: str | None = None

    bio: str | None = None
    phone: str | None = None
    discord: str | None = None
    telegram: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    def validate_data(cls, values):
        """Reject a payload in which every updatable field is ``None``."""

        if not any(key for key in values if key != "id" and values[key] is not None):
            raise ValueError("At least one updatable field must be provided.")
        return values


class UserResponse(UserBase):
    """Full user representation returned by the API."""

    id: int
    created_at: datetime
    updated_at: datetime | None = None
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
