"""Request/response schemas for free-form GM ASI adjustments (no class level)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import MAX_ABILITY_SCORE_CAP, AbilityScore


class GmAsiIncreaseItem(BaseModel):
    """One free-form ability adjustment applied by a GM (amounts may be negative)."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    amount: int


class GmAsiIncreaseInput(GmAsiIncreaseItem):
    """A requested adjustment: non-zero and within the ability-score cap either way."""

    amount: int = Field(ge=-MAX_ABILITY_SCORE_CAP, le=MAX_ABILITY_SCORE_CAP)

    @field_validator("amount")
    @classmethod
    def validate_non_zero(cls, amount: int) -> int:
        """A zero adjustment records nothing."""

        if amount == 0:
            raise ValueError("An ASI adjustment amount must not be zero.")
        return amount


class GmAsiChoiceAdd(BaseModel):
    """Add one GM ASI adjustment: a set of ±ability changes, no level attached."""

    increases: list[GmAsiIncreaseInput] = Field(min_length=1, max_length=len(AbilityScore))

    @field_validator("increases")
    @classmethod
    def validate_increases(cls, increases):
        """Reject a choice that lists the same ability more than once."""

        abilities = [item.ability for item in increases]
        if len(abilities) != len(set(abilities)):
            raise ValueError("Duplicate ability in an ASI choice is not allowed.")
        return increases


class GmAsiChoiceResponse(BaseModel):
    """A recorded GM ASI adjustment (``character_asi_choices`` row with no class level)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    increases: list[GmAsiIncreaseItem] = Field(default_factory=list)
