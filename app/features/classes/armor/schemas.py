"""Request/response schemas for a class's armor proficiencies."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import ArmorProficiency


def _validate_unique_armor_proficiencies(armor_proficiencies: list[ArmorProficiency]) -> list[ArmorProficiency]:
    """Reject duplicate armor proficiencies."""

    if len(armor_proficiencies) != len(set(armor_proficiencies)):
        raise ValueError("Duplicate armor proficiencies are not allowed.")

    return armor_proficiencies


class ArmorProficienciesUpdate(BaseModel):
    """Full replacement list of armor proficiencies for a class."""

    armor_proficiencies: list[ArmorProficiency]

    @field_validator("armor_proficiencies")
    def validate_unique(cls, v):
        """Reject duplicate armor proficiencies."""

        return _validate_unique_armor_proficiencies(v)


class ArmorProficiencyResponse(BaseModel):
    """A class's armor proficiency, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    armor_type: ArmorProficiency
