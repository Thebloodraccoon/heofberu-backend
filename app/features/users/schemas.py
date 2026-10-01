"""Request/response schemas for user management."""

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, model_validator

from app.constants import UserRole
from app.features.users.validators import Bio, ContactField, Email, NewPassword, Username


class UserBase(BaseModel):
    """Base user fields shared by create and response schemas (no input rules: stored data is trusted)."""

    username: str
    role: UserRole = UserRole.PLAYER
    email: str

    bio: str | None = None
    phone: str | None = None
    discord: str | None = None
    telegram: str | None = None


class UserCreate(UserBase):
    """Payload for creating a user, adding the plaintext ``password``."""

    username: Username
    email: Email
    password: NewPassword

    bio: Bio | None = None
    phone: ContactField | None = None
    discord: ContactField | None = None
    telegram: ContactField | None = None


class UserProfileUpdate(BaseModel):
    """
    Self-service partial update for the personal cabinet — no ``role`` field.

    At least one field must be sent; an explicit ``null`` is allowed only for
    the nullable free-text fields (it clears them), never for ``username``/``email``.
    """

    username: Username | None = None
    email: Email | None = None

    bio: Bio | None = None
    phone: ContactField | None = None
    discord: ContactField | None = None
    telegram: ContactField | None = None

    model_config = ConfigDict(extra="forbid")

    NON_NULLABLE_FIELDS: ClassVar[tuple[str, ...]] = ("username", "email")

    @model_validator(mode="after")
    def validate_data(self):
        """Reject an empty payload and explicit ``null`` for non-nullable fields."""

        if not self.model_fields_set:
            raise ValueError("At least one updatable field must be provided.")

        for name in self.NON_NULLABLE_FIELDS:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")

        return self


class UserUpdate(UserProfileUpdate):
    """Partial-update payload for managers: the profile fields plus ``role``."""

    role: UserRole | None = None

    NON_NULLABLE_FIELDS: ClassVar[tuple[str, ...]] = ("username", "email", "role")


class UserResponse(UserBase):
    """Full user representation returned by the API."""

    id: int
    created_at: datetime
    updated_at: datetime | None = None
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
