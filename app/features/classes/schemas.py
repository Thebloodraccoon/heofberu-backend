from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore


class ClassBase(BaseModel):
    name: str
    hit_dice: str
    skill_choice_count: int = 2
    spellcasting_ability: AbilityScore | None = None
    description: str = ""
    is_homebrew: bool = False


class ClassCreate(ClassBase):
    primary_abilities: list[AbilityScore] = []
    saving_throws: list[AbilityScore] = []

    @field_validator("primary_abilities")
    def validate_unique_primary_abilities(cls, primary_abilities):
        if len(primary_abilities) != len(set(primary_abilities)):
            raise ValueError("Duplicate primary abilities are not allowed.")
        return primary_abilities

    @field_validator("saving_throws")
    def validate_unique_saving_throws(cls, saving_throws):
        if len(saving_throws) != len(set(saving_throws)):
            raise ValueError("Duplicate saving throws are not allowed.")
        return saving_throws


class ClassUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    hit_dice: str | None = None
    skill_choice_count: int | None = None
    spellcasting_ability: AbilityScore | None = None
    description: str | None = None
    is_homebrew: bool | None = None
    primary_abilities: list[AbilityScore] | None = None
    saving_throws: list[AbilityScore] | None = None

    @field_validator("primary_abilities")
    def validate_unique_primary_abilities(cls, primary_abilities):
        if primary_abilities is None:
            return primary_abilities
        if len(primary_abilities) != len(set(primary_abilities)):
            raise ValueError("Duplicate primary abilities are not allowed.")
        return primary_abilities

    @field_validator("saving_throws")
    def validate_unique_saving_throws_update(cls, saving_throws):
        if saving_throws is None:
            return saving_throws
        if len(saving_throws) != len(set(saving_throws)):
            raise ValueError("Duplicate saving throws are not allowed.")
        return saving_throws


class SavingThrowsUpdate(BaseModel):
    """Full replacement list of saving throw proficiencies for a class."""

    saving_throws: list[AbilityScore]

    @field_validator("saving_throws")
    def validate_unique_saving_throws(cls, saving_throws):
        if len(saving_throws) != len(set(saving_throws)):
            raise ValueError("Duplicate saving throws are not allowed.")
        return saving_throws


class AvailableSkillsUpdate(BaseModel):
    """Full replacement list of skill IDs a class may choose proficiencies from."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Duplicate skill IDs are not allowed.")
        return skill_ids


class PrimaryAbilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class SavingThrowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    ability: AbilityScore
    description: str


class ClassResponse(ClassBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None
    primary_abilities: list[PrimaryAbilityResponse] = []
    saving_throws: list[SavingThrowResponse] = []
    available_skills: list[SkillResponse] = []
