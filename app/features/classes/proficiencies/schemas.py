"""Request/response schemas for a class's saving throws, armor and weapon proficiencies."""

from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore, ArmorProficiency, WeaponProficiency
from app.features.classes.schema_utils import unique_items


class SavingThrowsUpdate(BaseModel):
    """Full replacement list of saving throw proficiencies for a class."""

    saving_throws: list[AbilityScore]

    _unique = unique_items("saving_throws", "saving throws")


class ArmorProficienciesUpdate(BaseModel):
    """Full replacement list of armor proficiencies for a class."""

    armor_proficiencies: list[ArmorProficiency]

    _unique = unique_items("armor_proficiencies", "armor proficiencies")


class WeaponProficienciesUpdate(BaseModel):
    """Full replacement list of weapon proficiencies for a class."""

    weapon_proficiencies: list[WeaponProficiency]

    _unique = unique_items("weapon_proficiencies", "weapon proficiencies")


class SavingThrowResponse(BaseModel):
    """A class's saving throw proficiency, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class ArmorProficiencyResponse(BaseModel):
    """A class's armor proficiency, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    armor_type: ArmorProficiency


class WeaponProficiencyResponse(BaseModel):
    """A class's weapon proficiency, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    weapon_category: WeaponProficiency
