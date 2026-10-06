"""Schemas and bounded field types shared by the race and subrace catalogs (neither package imports the other)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.constants import AbilityScore

NAME_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 10_000
SPEED_MAX = 200
ABILITY_BONUS_LIMIT = 10
MAX_ID_LIST_LENGTH = 100

CatalogName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH)]
Description = Annotated[str, Field(max_length=DESCRIPTION_MAX_LENGTH)]
Speed = Annotated[int, Field(ge=0, le=SPEED_MAX)]


class PartialUpdate(BaseModel):
    """PATCH payload base: omitted fields are left alone, an explicit ``null`` is rejected (no field is nullable)."""

    @model_validator(mode="after")
    def reject_explicit_null(self):
        """Fail validation (422) instead of letting a NOT NULL violation surface from the database."""

        nulls = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulls:
            raise ValueError(f"Fields cannot be null: {', '.join(nulls)}")

        return self


class AbilityBonusItem(BaseModel):
    """A single ability score bonus, e.g. {"ability": "DEX", "bonus": 2}."""

    ability: AbilityScore
    bonus: int = Field(ge=-ABILITY_BONUS_LIMIT, le=ABILITY_BONUS_LIMIT)


class AbilityBonusResponse(BaseModel):
    """An ability score bonus as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    bonus: int


class AbilityBonusesUpdate(BaseModel):
    """Full replacement list of ability bonuses (one entry per ability score at most)."""

    ability_bonuses: list[AbilityBonusItem] = Field(max_length=len(AbilityScore))

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, ability_bonuses):
        """Reject bonus lists containing duplicate ability scores."""

        abilities = [item.ability for item in ability_bonuses]
        if len(abilities) != len(set(abilities)):
            duplicates = {a for a in abilities if abilities.count(a) > 1}
            raise ValueError(f"Duplicate ability score(s): {sorted(duplicates)}")

        return ability_bonuses


class SubraceBrief(BaseModel):
    """Lightweight subrace row: the ``GET /subraces`` listing and ``RaceResponse.subraces``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    race_id: int
    name: str
    image_url: str | None = None
