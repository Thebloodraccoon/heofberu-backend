"""Request/response schemas for the skill endpoints."""

from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore


class SkillBase(BaseModel):
    """Base skill fields shared by create and response schemas."""

    key: str
    name: str
    ability: AbilityScore
    description: str = ""


class SkillCreate(SkillBase):
    """Payload for creating a skill (GM only)."""


class SkillUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    key: str | None = None
    name: str | None = None
    ability: AbilityScore | None = None
    description: str | None = None


class SkillResponse(SkillBase):
    """Full skill representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class SkillBriefResponse(BaseModel):
    """Lightweight listing row: no description."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    ability: AbilityScore
