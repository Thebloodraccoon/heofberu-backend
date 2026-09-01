"""Schemas for conditions on a character."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import ConditionType


class CharacterConditionAdd(BaseModel):
    """Record an active condition. ``exhaustion_level`` (1-6) is required iff the condition is ``EXHAUSTION``."""

    condition: ConditionType
    exhaustion_level: int | None = Field(default=None, ge=1, le=6)
    source: str = ""

    @model_validator(mode="after")
    def _validate_exhaustion_level(self):
        """Enforce the EXHAUSTION exhaustion-level rules on the payload."""

        if self.condition == ConditionType.EXHAUSTION and self.exhaustion_level is None:
            raise ValueError("exhaustion_level is required when condition is EXHAUSTION (1-6).")
        if self.condition != ConditionType.EXHAUSTION and self.exhaustion_level is not None:
            raise ValueError("exhaustion_level is only valid when condition is EXHAUSTION.")
        return self


class CharacterConditionUpdate(BaseModel):
    """Change a condition's ``exhaustion_level`` or ``source`` (the condition itself is fixed by the path)."""

    exhaustion_level: int | None = Field(default=None, ge=1, le=6)
    source: str | None = None


class CharacterConditionResponse(BaseModel):
    """An active condition on a character."""

    model_config = ConfigDict(from_attributes=True)

    character_id: int
    condition: ConditionType
    exhaustion_level: int | None = None
    source: str = ""
