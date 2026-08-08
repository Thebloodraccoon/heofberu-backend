"""Request/response schemas for the race endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore, RaceSize
from app.features.features.schemas import FeatureBriefResponse, NestedFeatureCreate


class RaceBase(BaseModel):
    """Base race fields shared by create, update, and response schemas."""

    name: str
    size: RaceSize = RaceSize.MEDIUM
    speed: int = 30
    description: str = ""
    is_homebrew: bool = False


class AbilityBonusItem(BaseModel):
    """A single ability score bonus, e.g. {"ability": "DEX", "bonus": 2}."""

    ability: AbilityScore
    bonus: int


def _validate_unique_abilities(ability_bonuses: list[AbilityBonusItem]) -> list[AbilityBonusItem]:
    abilities = [item.ability for item in ability_bonuses]
    if len(abilities) != len(set(abilities)):
        duplicates = {a for a in abilities if abilities.count(a) > 1}
        raise ValueError(f"Duplicate ability score(s): {sorted(duplicates)}")
    return ability_bonuses


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")
    return skill_ids


class RaceCreate(RaceBase):
    """
    Create payload for a race.

    ``ability_bonuses`` and ``granted_skills`` are optional — a race can be
    created without them (matching prior behavior) or with them supplied
    up front, avoiding the extra PUT round-trips. When provided, semantics
    are "full replace from empty", same as the dedicated PUT endpoints.
    """

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
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Deliberately does NOT include ability_bonuses/granted_skills: those keep
    their own PUT endpoints with explicit full-replace semantics, since PATCH's
    "only touch what's set" doesn't map cleanly onto "replace the whole list".
    """

    name: str | None = None
    size: RaceSize | None = None
    speed: int | None = None
    description: str | None = None
    is_homebrew: bool | None = None


class AbilityBonusesUpdate(BaseModel):
    """Full replacement list of ability bonuses for a race."""

    ability_bonuses: list[AbilityBonusItem]

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, ability_bonuses):
        """Reject bonus lists containing duplicate ability scores."""
        return _validate_unique_abilities(ability_bonuses)


class AbilityBonusResponse(BaseModel):
    """A race's ability score bonus as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    bonus: int


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
    created_by_id: int | None = None
    ability_bonuses: list[AbilityBonusResponse] = []
    granted_skills: list[SkillResponse] = []
    features: list[FeatureBriefResponse] = []


class RaceBriefResponse(BaseModel):
    """
    Lightweight listing row: no ability bonuses / granted skills, no description.

    Served by the inherited ``BaseService.list_brief`` column-select path
    (``BaseRepository.get_brief``), which loads only these columns, is
    paginated, and is ordered by ``Race.id``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    size: RaceSize
    is_homebrew: bool
