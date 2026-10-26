"""Request/response schemas for the weapon-property dictionary."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

PropertyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class WeaponPropertyCreate(BaseModel):
    """A new weapon property; the flags say which item fields a weapon with it must fill."""

    model_config = ConfigDict(extra="forbid")

    name: PropertyName
    description: str = ""
    requires_range: bool = False
    requires_versatile_damage: bool = False


class WeaponPropertyUpdate(BaseModel):
    """PATCH a weapon property; ``null`` is rejected (every column is NOT NULL)."""

    model_config = ConfigDict(extra="forbid")

    name: PropertyName | None = None
    description: str | None = None
    requires_range: bool | None = None
    requires_versatile_damage: bool | None = None

    @field_validator("*")
    @classmethod
    def reject_explicit_null(cls, value):
        """Omit a field to leave it unchanged."""

        if value is None:
            raise ValueError("This field cannot be null; omit it to leave it unchanged.")
        return value


class WeaponPropertyResponse(BaseModel):
    """A weapon property with its rules text and required-field flags."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str = ""
    requires_range: bool = False
    requires_versatile_damage: bool = False
