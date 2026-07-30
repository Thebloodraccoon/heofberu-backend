from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore


class SkillProficiencyItem(BaseModel):
    skill_id: int
    is_expertise: bool = False


class SkillProficienciesUpdate(BaseModel):
    """Full replacement list of a character's skill proficiencies."""

    skill_proficiencies: list[SkillProficiencyItem]


class SavingThrowProficienciesUpdate(BaseModel):
    """Full replacement list of a character's saving throw proficiencies."""

    saving_throws: list[AbilityScore]


class SkillProficiencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool


class SavingThrowProficiencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
