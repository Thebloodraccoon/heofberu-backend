"""Request/response schemas for the skill endpoints."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.constants import AbilityScore

# Input bound follows the column size; responses stay unconstrained so legacy rows always serialize.
SkillName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SkillBase(BaseModel):
    """Base skill fields shared by create and response schemas."""

    name: str
    ability: AbilityScore
    description: str = ""


class SkillCreate(SkillBase):
    """Payload for creating a skill (GM only)."""

    name: SkillName


class SkillUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics); ``null`` is rejected."""

    name: SkillName | None = None
    ability: AbilityScore | None = None
    description: str | None = None

    @field_validator("name", "ability", "description")
    @classmethod
    def reject_explicit_null(cls, value):
        """Every field maps to a NOT NULL column: omit it to leave it unchanged."""

        if value is None:
            raise ValueError("This field cannot be null; omit it to leave it unchanged.")

        return value


class SkillResponse(SkillBase):
    """Full skill representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class SkillGetAllResponse(BaseModel):
    """Lightweight listing row: no description."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ability: AbilityScore
