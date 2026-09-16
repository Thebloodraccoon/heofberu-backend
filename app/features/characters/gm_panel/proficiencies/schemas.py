"""Request schemas for GM management of a character's proficiency rows."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore, ArmorProficiency, WeaponProficiency


class SkillProficiencyAdd(BaseModel):
    """Grant a character proficiency in a skill (free-form, no feature behind it)."""

    skill_id: int


class SkillExpertiseUpdate(BaseModel):
    """Toggle expertise on one of the character's skill proficiencies."""

    model_config = ConfigDict(extra="forbid")

    is_expertise: bool


class SavingThrowProficiencyAdd(BaseModel):
    """Grant a character proficiency in a saving throw."""

    ability: AbilityScore


class ArmorProficiencyAdd(BaseModel):
    """Grant a character proficiency in an armor category."""

    armor_type: ArmorProficiency


class WeaponProficiencyAdd(BaseModel):
    """Grant a character proficiency in a weapon category or a single item — exactly one of the two."""

    weapon_category: WeaponProficiency | None = None
    item_id: int | None = None

    @field_validator("item_id")
    @classmethod
    def validate_exactly_one_target(cls, item_id: int | None, info):
        """Reject a payload that sets both or neither of ``weapon_category``/``item_id``."""

        weapon_category = info.data.get("weapon_category")
        if (weapon_category is None) == (item_id is None):
            raise ValueError("Provide exactly one of weapon_category or item_id.")

        return item_id
