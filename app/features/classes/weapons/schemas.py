"""Request/response schemas for a class's weapon proficiencies."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import WeaponProficiency


def _validate_unique_weapon_proficiencies(weapon_proficiencies: list[WeaponProficiency]) -> list[WeaponProficiency]:
    """Reject duplicate weapon proficiencies."""

    if len(weapon_proficiencies) != len(set(weapon_proficiencies)):
        raise ValueError("Duplicate weapon proficiencies are not allowed.")

    return weapon_proficiencies


class WeaponProficienciesUpdate(BaseModel):
    """Full replacement list of weapon proficiencies for a class."""

    weapon_proficiencies: list[WeaponProficiency]

    @field_validator("weapon_proficiencies")
    def validate_unique(cls, v):
        """Reject duplicate weapon proficiencies."""

        return _validate_unique_weapon_proficiencies(v)


class WeaponProficiencyResponse(BaseModel):
    """A class's weapon proficiency, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    weapon_category: WeaponProficiency
