"""Request/response schemas for a race's granted skills."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    """Reject lists containing duplicate skill IDs."""

    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")

    return skill_ids


class SkillsUpdate(BaseModel):
    """Full replacement list of skill IDs granted by a race."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        """Reject lists containing duplicate skill IDs."""

        return _validate_unique_skill_ids(skill_ids)


class SkillResponse(BaseModel):
    """Brief skill representation embedded in race responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ability: AbilityScore
    description: str
