"""Request/response schemas for a race's granted skills."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import AbilityScore
from app.core.types import EntityId
from app.features.shared.catalog.schemas import MAX_ID_LIST_LENGTH


class SkillsUpdate(BaseModel):
    """Full replacement list of skill IDs granted by a race."""

    skill_ids: list[EntityId] = Field(max_length=MAX_ID_LIST_LENGTH)

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        """Reject lists containing duplicate skill IDs."""

        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Duplicate skill IDs are not allowed.")

        return skill_ids


class SkillResponse(BaseModel):
    """Brief skill representation embedded in race responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ability: AbilityScore
    description: str
