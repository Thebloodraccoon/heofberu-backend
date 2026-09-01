"""Shared ability-bonus primitives for the race and subrace schemas."""

from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore


class AbilityBonusItem(BaseModel):
    """A single ability score bonus, e.g. {"ability": "DEX", "bonus": 2}."""

    ability: AbilityScore
    bonus: int


class AbilityBonusResponse(BaseModel):
    """An ability score bonus as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    bonus: int


def _validate_unique_abilities(ability_bonuses: list[AbilityBonusItem]) -> list[AbilityBonusItem]:
    """Reject bonus lists containing duplicate ability scores."""

    abilities = [item.ability for item in ability_bonuses]
    if len(abilities) != len(set(abilities)):
        duplicates = {a for a in abilities if abilities.count(a) > 1}
        raise ValueError(f"Duplicate ability score(s): {sorted(duplicates)}")

    return ability_bonuses
