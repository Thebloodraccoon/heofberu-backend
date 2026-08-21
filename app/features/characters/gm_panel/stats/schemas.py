"""Schemas for the GM stats overview (original base vs computed totals)."""

from pydantic import BaseModel


class AbilityScoreView(BaseModel):
    """One ability's original (base) value next to its effective total."""

    base: int
    total: int


class GmCharacterStatsResponse(BaseModel):
    """
    GM view of a character's six abilities: the ORIGINAL base values
    (what the player entered plus level-up/GM bumps on the base columns)
    alongside the COMPUTED effective totals (base + race/subrace/feat
    bonuses), freshly calculated — never the stale cache.
    """

    strength: AbilityScoreView
    dexterity: AbilityScoreView
    constitution: AbilityScoreView
    intelligence: AbilityScoreView
    wisdom: AbilityScoreView
    charisma: AbilityScoreView
