"""Request/response schemas for a class's available skills."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    """Reject duplicate skill IDs."""

    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")

    return skill_ids


class AvailableSkillsUpdate(BaseModel):
    """Full replacement list of skill IDs a class may choose proficiencies from."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique(cls, v):
        """Reject duplicate skill IDs."""

        return _validate_unique_skill_ids(v)


class SkillResponse(BaseModel):
    """Brief skill representation embedded in class responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ability: AbilityScore
    description: str
