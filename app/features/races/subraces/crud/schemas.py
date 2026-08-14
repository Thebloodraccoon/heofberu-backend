"""Request/response schemas for the subrace CRUD endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.features.races.ability_bonuses.schemas import (
    AbilityBonusItem,
    AbilityBonusResponse,
    _validate_unique_abilities,
)
from app.features.shared.features.schemas import NestedFeatureCreate


class SubraceBase(BaseModel):
    """Base subrace fields shared by create, update, and response schemas."""

    name: str
    description: str = ""


class SubraceCreate(SubraceBase):
    """
    Create payload for a subrace (nested under a race).

    ``ability_bonuses`` and ``features`` are optional — they can be supplied
    up front or filled later through the dedicated PUT/POST endpoints.
    """

    ability_bonuses: list[AbilityBonusItem] | None = None
    features: list[NestedFeatureCreate] | None = None

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, value):
        """Reject bonus lists containing duplicate ability scores."""

        if value is None:
            return value

        return _validate_unique_abilities(value)


class SubraceUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Deliberately does NOT include ability_bonuses: that list keeps its own
    PUT endpoint with explicit full-replace semantics.
    """

    name: str | None = None
    description: str | None = None


class SubraceAbilityBonusesUpdate(BaseModel):
    """Full replacement list of ability bonuses for a subrace."""

    ability_bonuses: list[AbilityBonusItem]

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, ability_bonuses):
        """Reject bonus lists containing duplicate ability scores."""

        return _validate_unique_abilities(ability_bonuses)


class SubraceResponse(SubraceBase):
    """Full subrace representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    race_id: int
    created_by_id: int | None = None
    ability_bonuses: list[AbilityBonusResponse] = []


class SubraceBriefResponse(BaseModel):
    """Compact subrace row for embedding inside race responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    race_id: int
    name: str
