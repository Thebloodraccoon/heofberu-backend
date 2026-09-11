"""Request/response schemas for a class's saving throw proficiencies."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore


def _validate_unique_saving_throws(saving_throws: list[AbilityScore]) -> list[AbilityScore]:
    """Reject duplicate saving throws."""

    if len(saving_throws) != len(set(saving_throws)):
        raise ValueError("Duplicate saving throws are not allowed.")

    return saving_throws


class SavingThrowsUpdate(BaseModel):
    """Full replacement list of saving throw proficiencies for a class."""

    saving_throws: list[AbilityScore]

    @field_validator("saving_throws")
    def validate_unique(cls, v):
        """Reject duplicate saving throws."""

        return _validate_unique_saving_throws(v)


class SavingThrowResponse(BaseModel):
    """A class's saving throw proficiency, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
