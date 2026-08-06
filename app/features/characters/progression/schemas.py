"""Schemas for character progression: race/class change and leveling up."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import AbilityScore, ASILevelChoice

# A single ASI at a level grants up to +2 total across the six abilities
# (e.g. +2 to one ability, or +1/+1 to two). Individual increments are
# bounded 1..2 and the total is validated to stay within that budget.
ASI_TOTAL_BUDGET = 2


class RaceChange(BaseModel):
    """Change a character's race. ``race_id: null`` clears it."""

    race_id: int | None = None


class ClassChange(BaseModel):
    """Change a character's class (full replacement — no multiclassing)."""

    class_id: int


class ASIIncreaseItem(BaseModel):
    """One increment of an Ability Score Improvement, e.g. {"ability": "STR", "amount": 2}."""

    ability: AbilityScore
    amount: int = Field(default=1, ge=1, le=ASI_TOTAL_BUDGET)


def _validate_asi_increases(increases: list[ASIIncreaseItem]) -> list[ASIIncreaseItem]:
    """Reject duplicate abilities and totals outside the +1..+2 ASI budget."""
    abilities = [item.ability for item in increases]
    if len(abilities) != len(set(abilities)):
        raise ValueError("Duplicate ability in an ASI choice is not allowed.")
    total = sum(item.amount for item in increases)
    if not (1 <= total <= ASI_TOTAL_BUDGET):
        raise ValueError(f"An ASI choice must grant between 1 and {ASI_TOTAL_BUDGET} total points.")
    return increases


class ASIChoice(BaseModel):
    """Level-up choice taking the Ability Score Improvement option."""

    type: Literal["ASI"] = "ASI"
    increases: list[ASIIncreaseItem]

    @field_validator("increases")
    def validate_increases(cls, increases):
        return _validate_asi_increases(increases)


class FeatChoice(BaseModel):
    """
    Level-up choice taking a feat instead of the Ability Score Improvement.

    ``ability_score_increase_id`` is optional, mirroring the manual feat
    grant: if the chosen feat offers an ASI of its own (e.g. Resilient),
    pass the id of the specific ``FeatAbilityScoreIncrease`` row to apply.
    """

    type: Literal["FEAT"] = "FEAT"
    feat_id: int
    ability_score_increase_id: int | None = None


LevelUpChoice = Annotated[ASIChoice | FeatChoice, Field(discriminator="type")]


class LevelUpRequest(BaseModel):
    """
    Level a character up exactly one level.

    ``hit_points_gained`` is optional: when omitted, the standard average
    (half the class hit die + 1 + CON modifier) is used; when provided it
    must be within ``[1, hit die + CON modifier]``.

    ``choice`` is required when the new level is an Ability Score
    Improvement level and rejected otherwise. See ``ASI_LEVELS``.
    """

    hit_points_gained: int | None = Field(default=None, ge=1)
    choice: LevelUpChoice | None = None


class ASIIncreaseResponse(BaseModel):
    """A single increment of a recorded ASI choice."""

    ability: AbilityScore
    amount: int


class CharacterASIChoiceResponse(BaseModel):
    """A recorded ASI-level resolution for a character."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    class_level: int
    choice_type: ASILevelChoice
    feat_id: int | None = None
    ability_score_increase_id: int | None = None
    increases: list[ASIIncreaseResponse] = []
