"""Schemas for character skill and saving-throw proficiencies."""

from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore


class SkillProficiencyItem(BaseModel):
    """A single skill proficiency entry: ``skill_id`` plus an expertise flag."""

    skill_id: int
    is_expertise: bool = False


class SkillProficienciesUpdate(BaseModel):
    """Full replacement list of a character's skill proficiencies."""

    skill_proficiencies: list[SkillProficiencyItem]


class SavingThrowProficienciesUpdate(BaseModel):
    """Full replacement list of a character's saving throw proficiencies."""

    saving_throws: list[AbilityScore]


class SkillProficiencyResponse(BaseModel):
    """A skill proficiency row returned on the character."""

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool


class SavingThrowProficiencyResponse(BaseModel):
    """A saving throw proficiency row returned on the character."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
