"""Schemas for a character's proficiency surface, each row tagged with the grant it came from."""

from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore, ArmorProficiency, FeatureSourceType, GrantSource, WeaponProficiency


class ProficiencySource(BaseModel):
    """
    Where one proficiency row came from. ``grant_source`` is None for a raw
    free-form row (``source_character_feature_id`` is NULL — a GM toggle or
    a pre-engine player pick); otherwise it mirrors the granting
    ``CharacterFeature.grant_source`` (AUTO/GM/ASI), and ``feature_*``
    identifies the reference ``Feature`` (class/subclass/race/background/feat)
    that produced it.
    """

    grant_source: GrantSource | None = None
    feature_id: int | None = None
    feature_name: str | None = None
    feature_source_type: FeatureSourceType | None = None


class SkillProficiencyView(BaseModel):
    """A materialized skill proficiency with its source."""

    skill_id: int
    is_expertise: bool
    source: ProficiencySource


class SavingThrowProficiencyView(BaseModel):
    """A materialized saving-throw proficiency with its source."""

    ability: AbilityScore
    source: ProficiencySource


class ArmorProficiencyView(BaseModel):
    """A materialized armor proficiency with its source."""

    armor_type: ArmorProficiency
    source: ProficiencySource


class WeaponProficiencyView(BaseModel):
    """A materialized weapon proficiency (category or item) with its source."""

    weapon_category: WeaponProficiency | None = None
    item_id: int | None = None
    source: ProficiencySource


class CharacterProficienciesResponse(BaseModel):
    """Combined read model behind ``GET /characters/{id}/proficiencies``."""

    model_config = ConfigDict(from_attributes=True)

    skills: list[SkillProficiencyView] = []
    saving_throws: list[SavingThrowProficiencyView] = []
    armor: list[ArmorProficiencyView] = []
    weapons: list[WeaponProficiencyView] = []
