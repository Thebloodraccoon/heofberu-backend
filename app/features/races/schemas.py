"""Request/response schemas for the race endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore, RaceSize
from app.features.features.crud.schemas import NestedFeatureCreate, NestedFeatureResponse
from app.features.races.ability_bonuses.schemas import (
    AbilityBonusItem,
    AbilityBonusResponse,
    _validate_unique_abilities,
)
from app.features.subraces.crud.schemas import SubraceBriefResponse


class RaceBase(BaseModel):
    """Base race fields shared by create, update, and response schemas."""

    name: str
    size: RaceSize = RaceSize.MEDIUM
    speed: int = 30
    description: str = ""
    image_url: str | None = None


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    """Reject lists containing duplicate skill IDs."""

    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")

    return skill_ids


class RaceCreate(RaceBase):
    """Create payload for a race with optional bonuses, skills, and features."""

    ability_bonuses: list[AbilityBonusItem] | None = None
    granted_skills: list[int] | None = None
    features: list[NestedFeatureCreate] | None = None

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, value):
        """Reject bonus lists containing duplicate ability scores."""

        if value is None:
            return value

        return _validate_unique_abilities(value)

    @field_validator("granted_skills")
    def validate_unique_skill_ids(cls, value):
        """Reject lists containing duplicate skill IDs."""

        if value is None:
            return value

        return _validate_unique_skill_ids(value)


class RaceUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    size: RaceSize | None = None
    speed: int | None = None
    description: str | None = None
    image_url: str | None = None


class AbilityBonusesUpdate(BaseModel):
    """Full replacement list of ability bonuses for a race."""

    ability_bonuses: list[AbilityBonusItem]

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, ability_bonuses):
        """Reject bonus lists containing duplicate ability scores."""

        return _validate_unique_abilities(ability_bonuses)


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
    key: str
    name: str
    ability: AbilityScore
    description: str


class RaceResponse(RaceBase):
    """Full race representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ability_bonuses: list[AbilityBonusResponse] = []
    granted_skills: list[SkillResponse] = []
    features: list[NestedFeatureResponse] = []
    subraces: list[SubraceBriefResponse] = []


class RaceGetAllResponse(BaseModel):
    """Lightweight listing row returned by the paginated ``GET /races`` endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    size: RaceSize
    image_url: str | None = None
