"""Request/response schemas for a class's available skills."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import AbilityScore
from app.features.classes.schema_utils import unique_items

MAX_AVAILABLE_SKILLS = 100


class AvailableSkillsUpdate(BaseModel):
    """Full replacement list of skill IDs a class may choose proficiencies from."""

    skill_ids: list[int] = Field(max_length=MAX_AVAILABLE_SKILLS)

    _unique = unique_items("skill_ids", "skill IDs")


class SkillResponse(BaseModel):
    """Brief skill representation embedded in class responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ability: AbilityScore
    description: str
