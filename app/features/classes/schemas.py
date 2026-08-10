"""Request/response schemas for the class endpoints."""

import math

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.constants import AbilityScore, DiceType, SpellLevel
from app.features.features.schemas import NestedFeatureCreate, NestedFeatureResponse


def _proficiency_bonus(class_level: int) -> int:
    """Return the proficiency bonus for a given class level (1-20)."""

    return math.ceil(class_level / 4) + 1


def _validate_unique_primary_abilities(primary_abilities: list[AbilityScore]) -> list[AbilityScore]:
    if len(primary_abilities) != len(set(primary_abilities)):
        raise ValueError("Duplicate primary abilities are not allowed.")

    return primary_abilities


def _validate_unique_saving_throws(saving_throws: list[AbilityScore]) -> list[AbilityScore]:
    if len(saving_throws) != len(set(saving_throws)):
        raise ValueError("Duplicate saving throws are not allowed.")

    return saving_throws


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")

    return skill_ids


def _validate_unique_spell_levels(slots: list["SpellSlotEntry"]) -> list["SpellSlotEntry"]:
    levels = [entry.spell_level for entry in slots]
    if len(levels) != len(set(levels)):
        raise ValueError("Duplicate spell_level entries are not allowed.")

    return slots


class SpellSlotEntry(BaseModel):
    """One row of a spell slot progression: slots of a given spell level at a given class level."""

    spell_level: SpellLevel
    slots: int = 0


class ClassSpellSlotProgressionCreate(BaseModel):
    """
    Spell slots a class grants at a single ``class_level``.

    Full replace: any ``spell_level`` for this ``class_level`` not included
    in ``slots`` is removed (slots reset to 0). Duplicate ``spell_level``
    entries are rejected. ``class_level`` must be within 1-20.
    """

    class_level: int
    slots: list[SpellSlotEntry]

    @field_validator("class_level")
    def validate_class_level(cls, class_level):
        if not (1 <= class_level <= 20):
            raise ValueError("class_level must be between 1 and 20.")
        return class_level

    @field_validator("slots")
    def validate_unique_spell_levels(cls, slots):
        return _validate_unique_spell_levels(slots)


class SubclassCreate(BaseModel):
    """
    Create payload for a subclass.

    ``features`` are created in the same transaction as the subclass itself
    with ``source_type=SUBCLASS`` and ``subclass_id`` set automatically.
    ``unlock_level`` defaults to 3 (most classes unlock at level 3); pass
    explicitly for classes that unlock earlier (1 for Cleric/Sorcerer/Warlock).
    """

    name: str
    archetype_group_name: str | None = None
    unlock_level: int = 3
    description: str = ""
    is_homebrew: bool = False
    features: list[NestedFeatureCreate] | None = None

    @field_validator("unlock_level")
    def validate_unlock_level(cls, v):
        if not (1 <= v <= 20):
            raise ValueError("unlock_level must be between 1 and 20.")
        return v


class SubclassUpdate(BaseModel):
    """All fields optional — PATCH semantics. Does not touch features."""

    name: str | None = None
    archetype_group_name: str | None = None
    unlock_level: int | None = None
    description: str | None = None
    is_homebrew: bool | None = None

    @field_validator("unlock_level")
    def validate_unlock_level(cls, v):
        if v is not None and not (1 <= v <= 20):
            raise ValueError("unlock_level must be between 1 and 20.")
        return v


class SubclassResponse(BaseModel):
    """Full subclass representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    name: str
    archetype_group_name: str | None = None
    unlock_level: int
    description: str
    is_homebrew: bool
    created_by_id: int | None = None


class SubclassBriefResponse(BaseModel):
    """Lightweight subclass row for listings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    name: str
    unlock_level: int
    is_homebrew: bool


class ClassBase(BaseModel):
    """Base class fields shared by create, update, and response schemas."""

    name: str
    hit_dice: DiceType
    skill_choice_count: int = 2
    spellcasting_ability: AbilityScore | None
    description: str = ""
    is_homebrew: bool = False


class ClassCreate(ClassBase):
    """
    Create payload for a class.

    ``features`` are CLASS-source features (e.g. Rage, Extra Attack).
    ``subclasses`` are created in the same transaction — each may carry
    its own nested ``features`` (SUBCLASS-source).
    ``available_skills``, ``primary_abilities``, ``saving_throws``, and
    ``spell_slot_progression`` are all optional and applied atomically.

    If ``spellcasting_ability`` is set (non-null) it must appear in
    ``primary_abilities``.
    """

    primary_abilities: list[AbilityScore] = []
    saving_throws: list[AbilityScore] = []
    available_skills: list[int] | None = None
    features: list[NestedFeatureCreate] | None = None
    subclasses: list[SubclassCreate] | None = None
    spell_slot_progression: list[ClassSpellSlotProgressionCreate] | None = None

    @field_validator("primary_abilities")
    def validate_unique_primary_abilities(cls, v):
        return _validate_unique_primary_abilities(v)

    @field_validator("saving_throws")
    def validate_unique_saving_throws(cls, v):
        return _validate_unique_saving_throws(v)

    @field_validator("available_skills")
    def validate_unique_available_skills(cls, v):
        if v is None:
            return v

        return _validate_unique_skill_ids(v)

    @model_validator(mode="after")
    def validate_spellcasting_ability_is_primary(self):
        """Ensure a non-null ``spellcasting_ability`` is also a primary ability."""

        if self.spellcasting_ability is not None and self.spellcasting_ability not in self.primary_abilities:
            raise ValueError(
                f"spellcasting_ability '{self.spellcasting_ability}' must also appear in primary_abilities."
            )

        return self

    @model_validator(mode="after")
    def validate_unique_class_levels(self):
        if self.spell_slot_progression:
            levels = [e.class_level for e in self.spell_slot_progression]
            if len(levels) != len(set(levels)):
                raise ValueError("Duplicate class_level entries in spell_slot_progression are not allowed.")

        return self


class ClassUpdate(BaseModel):
    """
    All fields optional — PATCH semantics.

    Does not include ``available_skills`` (dedicated PUT endpoint).
    Does not include ``features`` or ``subclasses`` — manage those through
    their own endpoints to keep replace-vs-patch semantics unambiguous.
    ``primary_abilities`` and ``saving_throws`` are full-replace when set.
    """

    name: str | None = None
    hit_dice: DiceType | None = None
    skill_choice_count: int | None = None
    spellcasting_ability: AbilityScore | None = None
    description: str | None = None
    is_homebrew: bool | None = None
    primary_abilities: list[AbilityScore] | None = None
    saving_throws: list[AbilityScore] | None = None

    @field_validator("primary_abilities")
    def validate_unique_primary_abilities(cls, v):
        if v is None:
            return v

        return _validate_unique_primary_abilities(v)

    @field_validator("saving_throws")
    def validate_unique_saving_throws_update(cls, v):
        if v is None:
            return v

        return _validate_unique_saving_throws(v)

    @model_validator(mode="after")
    def validate_spellcasting_ability_is_primary_if_both_set(self):
        """Ensure a non-null ``spellcasting_ability`` is primary when both are provided."""

        if (
            self.spellcasting_ability is not None
            and self.primary_abilities is not None
            and self.spellcasting_ability not in self.primary_abilities
        ):
            raise ValueError(
                f"spellcasting_ability '{self.spellcasting_ability}' must also appear in primary_abilities."
            )

        return self


class SavingThrowsUpdate(BaseModel):
    """Full replacement list of saving throw proficiencies for a class."""

    saving_throws: list[AbilityScore]

    @field_validator("saving_throws")
    def validate_unique(cls, v):
        return _validate_unique_saving_throws(v)


class AvailableSkillsUpdate(BaseModel):
    """Full replacement list of skill IDs a class may choose proficiencies from."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique(cls, v):
        return _validate_unique_skill_ids(v)


class SpellSlotProgressionUpdate(BaseModel):
    """
    Full replacement of the spell slots a class grants at a single
    ``class_level``. Any ``spell_level`` not included is reset to 0.
    """

    slots: list[SpellSlotEntry]

    @field_validator("slots")
    def validate_unique_spell_levels(cls, v):
        return _validate_unique_spell_levels(v)


class SpellSlotProgressionResponse(BaseModel):
    """Spell slots granted at one class level, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    class_level: int
    spell_level: SpellLevel
    slots: int


class PrimaryAbilityResponse(BaseModel):
    """A class's primary ability score, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class SavingThrowResponse(BaseModel):
    """A class's saving throw proficiency, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class SkillResponse(BaseModel):
    """Brief skill representation embedded in class responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    ability: AbilityScore
    description: str


class ClassResponse(ClassBase):
    """Full class representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None
    primary_abilities: list[PrimaryAbilityResponse] = []
    saving_throws: list[SavingThrowResponse] = []
    available_skills: list[SkillResponse] = []
    spell_slot_progression: list[SpellSlotProgressionResponse] = []
    subclasses: list[SubclassBriefResponse] = []


class SubclassListResponse(BaseModel):
    """Minimal subclass reference embedded in ``ClassGetAllResponse.subclasses``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ClassGetAllResponse(BaseModel):
    """Lightweight listing row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hit_dice: DiceType
    is_homebrew: bool = False
    subclasses: list[SubclassListResponse] = []


class ProgressionLevelRow(BaseModel):
    """
    One row of the class progression table — what a character gains at a
    given level. Returned by ``GET /classes/{id}/progression``.
    """

    level: int
    proficiency_bonus: int

    # spell slots: {spell_level → slots}, only levels with rows are included.
    # e.g. {"LEVEL_1": 4, "LEVEL_2": 2}  — absent means 0 slots.
    spell_slots: dict[str, int]

    # CLASS-source features gained at this level.
    class_features: list[NestedFeatureResponse]

    # SUBCLASS features grouped by subclass name, gained at this level.
    # Only populated for levels where at least one subclass grants a feature.
    subclass_features: list[NestedFeatureResponse]


class ClassProgressionResponse(BaseModel):
    """Full 1-20 progression table for a class."""

    class_id: int
    class_name: str
    rows: list[ProgressionLevelRow]
