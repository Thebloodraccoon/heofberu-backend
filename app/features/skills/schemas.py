from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore


class SkillBase(BaseModel):
    key: str
    name: str
    ability: AbilityScore
    description: str = ""


class SkillCreate(SkillBase):
    pass


class SkillUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    key: str | None = None
    name: str | None = None
    ability: AbilityScore | None = None
    description: str | None = None


class SkillResponse(SkillBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
