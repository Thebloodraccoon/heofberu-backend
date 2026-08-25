"""Request/response schemas for free-form GM ASI adjustments (no class level)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import AbilityScore


class GmAsiIncreaseItem(BaseModel):
    """
    One free-form ability adjustment applied by a GM.

    Unlike the level-up ASI there is no +1..+2 budget: amounts may be
    negative (lowering an ability) or arbitrarily large. The 20 cap is
    enforced by the service, not the schema.
    """

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    amount: int


class GmAsiChoiceAdd(BaseModel):
    """Add one GM ASI adjustment: a set of ±ability changes, no level attached."""

    increases: list[GmAsiIncreaseItem]

    @field_validator("increases")
    def validate_increases(cls, increases):
        abilities = [item.ability for item in increases]
        if len(abilities) != len(set(abilities)):
            raise ValueError("Duplicate ability in an ASI choice is not allowed.")
        return increases


class GmAsiChoiceResponse(BaseModel):
    """
    A recorded GM ASI adjustment (``character_asi_choices`` row with no
    class level). ``increases`` serializes the typed
    ``CharacterASIChoiceIncrease`` child rows.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    increases: list[GmAsiIncreaseItem] = Field(default_factory=list)
