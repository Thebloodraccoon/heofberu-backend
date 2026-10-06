"""Request schemas for GM management of a character's proficiency rows."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import AbilityScore, ArmorProficiency, WeaponProficiency


class SkillProficiencyAdd(BaseModel):
    """Grant a character proficiency in a skill (free-form, no feature behind it)."""

    skill_id: int = Field(gt=0)


class SkillProficiencyResponse(BaseModel):
    """A skill proficiency row as returned by the GM-panel skills endpoints."""

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool


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
    item_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_exactly_one_target(self):
        """Reject a payload that sets both or neither of ``weapon_category``/``item_id``."""

        if (self.weapon_category is None) == (self.item_id is None):
            raise ValueError("Provide exactly one of weapon_category or item_id.")

        return self
