"""Schemas for conditions on a character."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import ConditionType


class CharacterConditionAdd(BaseModel):
    """
    Record an active condition on a character.

    ``exhaustion_level`` (1-6) is required iff ``condition`` is
    ``EXHAUSTION`` — 5e tracks exhaustion in levels rather than as a
    boolean. ``source`` is a free-text note about where the condition
    came from.
    """

    condition: ConditionType
    exhaustion_level: int | None = Field(default=None, ge=1, le=6)
    source: str = ""

    @model_validator(mode="after")
    def _validate_exhaustion_level(self):
        if self.condition == ConditionType.EXHAUSTION and self.exhaustion_level is None:
            raise ValueError("exhaustion_level is required when condition is EXHAUSTION (1-6).")
        if self.condition != ConditionType.EXHAUSTION and self.exhaustion_level is not None:
            raise ValueError("exhaustion_level is only valid when condition is EXHAUSTION.")
        return self


class CharacterConditionUpdate(BaseModel):
    """
    Change a condition's ``exhaustion_level`` or ``source``.

    The condition itself is fixed by the URL path — remove it and re-add
    if the effect changes. ``exhaustion_level`` follows the same rules as
    on add (only valid for EXHAUSTION), validated against the resulting
    row in the service.
    """

    exhaustion_level: int | None = Field(default=None, ge=1, le=6)
    source: str | None = None


class CharacterConditionResponse(BaseModel):
    """An active condition on a character."""

    model_config = ConfigDict(from_attributes=True)

    character_id: int
    condition: ConditionType
    exhaustion_level: int | None = None
    source: str = ""
