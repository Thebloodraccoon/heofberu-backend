"""Request schema for a subrace's ability bonuses (shared primitives live in races/ability_bonuses/schemas.py)."""

from pydantic import BaseModel, field_validator

from app.features.races.ability_bonuses.schemas import AbilityBonusItem, _validate_unique_abilities


class SubraceAbilityBonusesUpdate(BaseModel):
    """Full replacement list of ability bonuses for a subrace."""

    ability_bonuses: list[AbilityBonusItem]

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, ability_bonuses):
        """Reject bonus lists containing duplicate ability scores."""

        return _validate_unique_abilities(ability_bonuses)
