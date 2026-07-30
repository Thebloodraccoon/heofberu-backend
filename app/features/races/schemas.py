from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore, RaceSize


class RaceBase(BaseModel):
    name: str
    size: RaceSize = RaceSize.MEDIUM
    speed: int = 30
    traits: str = ""
    description: str = ""
    is_homebrew: bool = False


class RaceCreate(RaceBase):
    pass


class RaceUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    size: RaceSize | None = None
    speed: int | None = None
    traits: str | None = None
    description: str | None = None
    is_homebrew: bool | None = None


class AbilityBonusItem(BaseModel):
    """A single ability score bonus, e.g. {"ability": "DEX", "bonus": 2}."""

    ability: AbilityScore
    bonus: int


class AbilityBonusesUpdate(BaseModel):
    """Full replacement list of ability bonuses for a race."""

    ability_bonuses: list[AbilityBonusItem]

    @field_validator("ability_bonuses")
    def validate_unique_abilities(cls, ability_bonuses):
        abilities = [item.ability for item in ability_bonuses]
        if len(abilities) != len(set(abilities)):
            duplicates = {a for a in abilities if abilities.count(a) > 1}
            raise ValueError(f"Duplicate ability score(s): {sorted(duplicates)}")
        return ability_bonuses


class AbilityBonusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    bonus: int


class SkillsUpdate(BaseModel):
    """Full replacement list of skill IDs granted by a race."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Duplicate skill IDs are not allowed.")
        return skill_ids


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    ability: AbilityScore
    description: str


class RaceResponse(RaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None
    ability_bonuses: list[AbilityBonusResponse] = []
    granted_skills: list[SkillResponse] = []
