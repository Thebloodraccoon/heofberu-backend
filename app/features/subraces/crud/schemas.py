"""Request/response schemas for the subrace CRUD endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.features.features.crud.schemas import NestedFeatureCreate, NestedFeatureResponse
from app.features.races.ability_bonuses.schemas import (
    AbilityBonusItem,
    AbilityBonusResponse,
    _validate_unique_abilities,
)


class SubraceBase(BaseModel):
    """Base subrace fields shared by create, update, and response schemas."""

    name: str
    race_id: int
    description: str = ""
    image_url: str | None = None


class SubraceCreate(SubraceBase):
    """Create payload for a subrace (nested under a race)."""

    ability_bonuses: list[AbilityBonusItem] | None = None
    features: list[NestedFeatureCreate] | None = None

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, value):
        """Reject bonus lists containing duplicate ability scores."""

        if value is None:
            return value

        return _validate_unique_abilities(value)


class SubraceUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    description: str | None = None
    image_url: str | None = None


class SubraceResponse(SubraceBase):
    """
    Full subrace representation returned by the API.

    Doubles as both the create/update response and the
    ``GET /subraces/{id}`` response: ``get_by_id`` folds the subrace's own
    SUBRACE-source ``features`` into it, while ``create``/``update`` return
    it with ``features`` at its empty default.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    race_id: int
    ability_bonuses: list[AbilityBonusResponse] = []
    features: list[NestedFeatureResponse] = []


class SubraceGetAllResponse(BaseModel):
    """Lightweight subrace row returned by ``GET /subraces`` and embedded in ``RaceResponse.subraces``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    race_id: int
    name: str
    image_url: str | None = None
