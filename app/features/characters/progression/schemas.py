"""Schemas for character progression: subclass/subrace/background setup, leveling up, rebuild."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import AbilityScore, ASILevelChoice

# A single ASI at a level grants up to +2 total across the six abilities
# (e.g. +2 to one ability, or +1/+1 to two). Individual increments are
# bounded 1..2 and the total is validated to stay within that budget.
ASI_TOTAL_BUDGET = 2


class SubclassChange(BaseModel):
    """
    Set or clear a character's subclass.

    ``subclass_id`` must reference a subclass of the character's current
    class (validated by the service); ``subclass_id: null`` clears it.
    Setting a subclass grants its features at or below the character's
    current level.
    """

    subclass_id: int | None = None


class SubraceChange(BaseModel):
    """
    Set or clear a character's subrace.

    ``subrace_id`` must reference a subrace of the character's current
    race (validated by the service; a character without a race cannot
    hold a subrace); ``subrace_id: null`` clears it. Setting a subrace
    grants its features at or below the character's current level.
    """

    subrace_id: int | None = None


class BackgroundChange(BaseModel):
    """

    Set a character's background — only allowed while the character has
    none (a background picked at creation can never be swapped).

    Grants everything a background grants at creation: its features (via
    progression sync), its granted skills (deduplicated against existing
    proficiencies), and its starting equipment (merged into existing
    stacks).
    """

    background_id: int


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

    ``ability_score_increase_id`` is required when the chosen feat offers
    ASI options of its own (e.g. Resilient) — pass the id of the specific
    ``FeatAbilityScoreIncrease`` row to apply; the service rejects a feat
    with options taken without one.
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


class CanLevelUpResponse(BaseModel):
    """
    Whether the character may take another level-up.

    ``max_level`` is the GM-set cap from ``character_max_levels``;
    leveling up is possible while ``current_level < max_level``.
    """

    can_level_up: bool
    current_level: int
    max_level: int


class ASIIncreaseResponse(BaseModel):
    """A single increment of a recorded ASI choice."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    amount: int


class CharacterASIChoiceResponse(BaseModel):
    """
    A recorded ASI-level resolution for a character. ``increases``
    serializes the typed ``CharacterASIChoiceIncrease`` child rows
    (empty for FEAT-type choices, whose stat effect flows through the
    granted feat).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    class_level: int | None = None
    choice_type: ASILevelChoice
    feat_id: int | None = None
    ability_score_increase_id: int | None = None
    increases: list[ASIIncreaseResponse] = Field(default_factory=list)
