"""Request/response schemas for the background granted-skill endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    """Reject lists containing duplicate skill IDs."""

    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")

    return skill_ids


class SkillsUpdate(BaseModel):
    """Full replacement list of skill IDs granted by a background."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        """Reject lists containing duplicate skill IDs."""

        return _validate_unique_skill_ids(skill_ids)


class SkillResponse(BaseModel):
    """Brief skill representation embedded in background responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: str
