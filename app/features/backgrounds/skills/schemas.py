"""Request/response schemas for the background granted-skill endpoints."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.types import EntityId


class SkillsUpdate(BaseModel):
    """Full replacement list of skill IDs granted by a background."""

    skill_ids: list[EntityId] = Field(max_length=200)

    @field_validator("skill_ids")
    @classmethod
    def validate_unique_skill_ids(cls, skill_ids: list[int]) -> list[int]:
        """Reject lists containing duplicate skill IDs."""

        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Duplicate skill IDs are not allowed.")

        return skill_ids


class SkillResponse(BaseModel):
    """Brief skill representation embedded in background responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
