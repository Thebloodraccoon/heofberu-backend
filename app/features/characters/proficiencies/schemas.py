"""Schemas for a character's proficiency surface, each row tagged with every source that grants it."""

from pydantic import BaseModel, ConfigDict

from app.constants import (
    AbilityScore,
    ArmorProficiency,
    FeatureSourceType,
    ProficiencySourceType,
    WeaponProficiency,
)


class ProficiencySource(BaseModel):
    """
    One source contributing to a resolved proficiency.

    ``feature_*`` is populated only for FEATURE/FEATURE_CHOICE rows
    (denormalized from the granting ``CharacterFeature``/reference
    ``Feature``, identifying the class/subclass/race/background/feat that
    produced it); ``actor_user_id`` only for a GM row. CLASS_CHOICE/RACE/
    BACKGROUND rows carry neither — ``source_type`` alone identifies them.
    """

    source_type: ProficiencySourceType
    feature_id: int | None = None
    feature_name: str | None = None
    feature_source_type: FeatureSourceType | None = None
    actor_user_id: int | None = None


class SkillProficiencyView(BaseModel):
    """
    A resolved skill proficiency with every source that grants it.

    Multiple sources are legitimate (e.g. class AND a feat both granting
    the same skill) — this is not deduplicated to one; ``is_expertise`` is
    the OR across all of them (any source wanting expertise turns it on).
    """

    skill_id: int
    is_expertise: bool
    sources: list[ProficiencySource]


class SavingThrowProficiencyView(BaseModel):
    """A resolved saving-throw proficiency with every source that grants it."""

    ability: AbilityScore
    sources: list[ProficiencySource]


class ArmorProficiencyView(BaseModel):
    """A resolved armor proficiency with every source that grants it."""

    armor_type: ArmorProficiency
    sources: list[ProficiencySource]


class WeaponProficiencyView(BaseModel):
    """A resolved weapon proficiency (category or item) with every source that grants it."""

    weapon_category: WeaponProficiency | None = None
    item_id: int | None = None
    sources: list[ProficiencySource]


class CharacterProficienciesResponse(BaseModel):
    """Combined read model behind ``GET /characters/{id}/proficiencies``."""

    model_config = ConfigDict(from_attributes=True)

    skills: list[SkillProficiencyView] = []
    saving_throws: list[SavingThrowProficiencyView] = []
    armor: list[ArmorProficiencyView] = []
    weapons: list[WeaponProficiencyView] = []
