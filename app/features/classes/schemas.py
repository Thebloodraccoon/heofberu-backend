"""Request/response schemas for the class endpoints (class-level only; see subclasses/crud/schemas.py)."""

import math

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore, ArmorProficiency, DiceType, SpellLevel, WeaponProficiency
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.shared.items.schemas import ChoiceGroupResponse, SourceItemResponse
from app.features.subclasses.crud.schemas import SubclassBriefResponse


def _proficiency_bonus(class_level: int) -> int:
    """Return the proficiency bonus for a given class level (1-20)."""

    return math.ceil(class_level / 4) + 1


def _validate_unique_saving_throws(saving_throws: list[AbilityScore]) -> list[AbilityScore]:
    """Reject duplicate saving throws."""

    if len(saving_throws) != len(set(saving_throws)):
        raise ValueError("Duplicate saving throws are not allowed.")

    return saving_throws


def _validate_unique_armor_proficiencies(armor_proficiencies: list[ArmorProficiency]) -> list[ArmorProficiency]:
    """Reject duplicate armor proficiencies."""

    if len(armor_proficiencies) != len(set(armor_proficiencies)):
        raise ValueError("Duplicate armor proficiencies are not allowed.")

    return armor_proficiencies


def _validate_unique_weapon_proficiencies(weapon_proficiencies: list[WeaponProficiency]) -> list[WeaponProficiency]:
    """Reject duplicate weapon proficiencies."""

    if len(weapon_proficiencies) != len(set(weapon_proficiencies)):
        raise ValueError("Duplicate weapon proficiencies are not allowed.")

    return weapon_proficiencies


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    """Reject duplicate skill IDs."""

    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")

    return skill_ids


def _validate_unique_spell_levels(slots: list["SpellSlotEntry"]) -> list["SpellSlotEntry"]:
    """Reject duplicate ``spell_level`` entries."""

    levels = [entry.spell_level for entry in slots]
    if len(levels) != len(set(levels)):
        raise ValueError("Duplicate spell_level entries are not allowed.")

    return slots


class SpellSlotEntry(BaseModel):
    """One row of a spell slot progression: slots of a given spell level at a given class level."""

    spell_level: SpellLevel
    slots: int = 0


class ClassSpellSlotProgressionCreate(BaseModel):
    """Spell slots a class grants at a single ``class_level`` (full replace)."""

    class_level: int
    slots: list[SpellSlotEntry]

    @field_validator("class_level")
    def validate_class_level(cls, class_level):
        """Ensure ``class_level`` is within 1-20."""

        if not (1 <= class_level <= 20):
            raise ValueError("class_level must be between 1 and 20.")
        return class_level

    @field_validator("slots")
    def validate_unique_spell_levels(cls, slots):
        """Reject duplicate ``spell_level`` entries."""

        return _validate_unique_spell_levels(slots)


class ClassBase(BaseModel):
    """Base class fields shared by create, update, and response schemas."""

    name: str
    hit_dice: DiceType
    skill_choice_count: int = 2
    spellcasting_ability: AbilityScore | None
    description: str = ""
    image_url: str | None = None


class ClassCreate(ClassBase):
    """
    Create payload for a class.

    Only scalar fields and directly-owned simple child rows
    (``saving_throws``, ``armor_proficiencies``, ``weapon_proficiencies``,
    ``available_skills``) are set here alongside the ``Class`` row.
    Features, subclasses, starting items, and spell slots are attached
    afterwards through their dedicated endpoints.
    """

    saving_throws: list[AbilityScore] = []
    armor_proficiencies: list[ArmorProficiency] = []
    weapon_proficiencies: list[WeaponProficiency] = []
    available_skills: list[int] | None = None

    @field_validator("saving_throws")
    def validate_unique_saving_throws(cls, v):
        """Reject duplicate saving throws."""

        return _validate_unique_saving_throws(v)

    @field_validator("armor_proficiencies")
    def validate_unique_armor_proficiencies(cls, v):
        """Reject duplicate armor proficiencies."""

        return _validate_unique_armor_proficiencies(v)

    @field_validator("weapon_proficiencies")
    def validate_unique_weapon_proficiencies(cls, v):
        """Reject duplicate weapon proficiencies."""

        return _validate_unique_weapon_proficiencies(v)

    @field_validator("available_skills")
    def validate_unique_available_skills(cls, v):
        """Reject duplicate skill IDs."""

        if v is None:
            return v

        return _validate_unique_skill_ids(v)


class ClassUpdate(BaseModel):
    """All fields optional — PATCH semantics. ``saving_throws``, ``armor_proficiencies`` and ``weapon_proficiencies`` are full-replace when set."""

    name: str | None = None
    hit_dice: DiceType | None = None
    skill_choice_count: int | None = None
    spellcasting_ability: AbilityScore | None = None
    description: str | None = None
    image_url: str | None = None
    saving_throws: list[AbilityScore] | None = None
    armor_proficiencies: list[ArmorProficiency] | None = None
    weapon_proficiencies: list[WeaponProficiency] | None = None

    @field_validator("saving_throws")
    def validate_unique_saving_throws_update(cls, v):
        """Reject duplicate saving throws when set."""

        if v is None:
            return v

        return _validate_unique_saving_throws(v)

    @field_validator("armor_proficiencies")
    def validate_unique_armor_proficiencies_update(cls, v):
        """Reject duplicate armor proficiencies when set."""

        if v is None:
            return v

        return _validate_unique_armor_proficiencies(v)

    @field_validator("weapon_proficiencies")
    def validate_unique_weapon_proficiencies_update(cls, v):
        """Reject duplicate weapon proficiencies when set."""

        if v is None:
            return v

        return _validate_unique_weapon_proficiencies(v)


class SavingThrowsUpdate(BaseModel):
    """Full replacement list of saving throw proficiencies for a class."""

    saving_throws: list[AbilityScore]

    @field_validator("saving_throws")
    def validate_unique(cls, v):
        """Reject duplicate saving throws."""

        return _validate_unique_saving_throws(v)


class ArmorProficienciesUpdate(BaseModel):
    """Full replacement list of armor proficiencies for a class."""

    armor_proficiencies: list[ArmorProficiency]

    @field_validator("armor_proficiencies")
    def validate_unique(cls, v):
        """Reject duplicate armor proficiencies."""

        return _validate_unique_armor_proficiencies(v)


class WeaponProficienciesUpdate(BaseModel):
    """Full replacement list of weapon proficiencies for a class."""

    weapon_proficiencies: list[WeaponProficiency]

    @field_validator("weapon_proficiencies")
    def validate_unique(cls, v):
        """Reject duplicate weapon proficiencies."""

        return _validate_unique_weapon_proficiencies(v)


class AvailableSkillsUpdate(BaseModel):
    """Full replacement list of skill IDs a class may choose proficiencies from."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique(cls, v):
        """Reject duplicate skill IDs."""

        return _validate_unique_skill_ids(v)


class SpellSlotProgressionUpdate(BaseModel):
    """Full replacement of the spell slots a class grants at one ``class_level``."""

    slots: list[SpellSlotEntry]

    @field_validator("slots")
    def validate_unique_spell_levels(cls, v):
        """Reject duplicate ``spell_level`` entries."""

        return _validate_unique_spell_levels(v)


class SpellSlotProgressionResponse(BaseModel):
    """Spell slots granted at one class level, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    class_level: int
    spell_level: SpellLevel
    slots: int


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
    saving_throws: list[SavingThrowResponse] = []
    armor_proficiencies: list[ArmorProficiencyResponse] = []
    weapon_proficiencies: list[WeaponProficiencyResponse] = []
    available_skills: list[SkillResponse] = []
    starting_items: list[SourceItemResponse] = []
    starting_choice_groups: list[ChoiceGroupResponse] = []
    spell_slot_progression: list[SpellSlotProgressionResponse] = []
    subclasses: list[SubclassBriefResponse] = []


class ClassGetAllResponse(BaseModel):
    """Lightweight listing row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hit_dice: DiceType
    subclasses: list["SubclassListResponse"] = []
    image_url: str | None = None


class ProgressionLevelRow(BaseModel):
    """One row of the class progression table for a given level."""

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


class ClassFullResponse(ClassResponse):
    """
    Everything about a class in one payload: base fields,
    saving throws/armor proficiencies/available skills/starting
    items/spell slots (all inherited from ``ClassResponse``), plus
    CLASS-source ``features`` and a brief reference to each subclass.

    Returned by ``GET /classes/{id}`` and cached as a single unit under
    the ``classes`` namespace.
    """

    features: list[NestedFeatureResponse] = []
    subclasses: list[SubclassBriefResponse] = []


# Forward ref to SubclassListResponse (subclasses/crud/schemas.py) to avoid a circular import.
from app.features.subclasses.crud.schemas import SubclassListResponse  # noqa: E402

ClassGetAllResponse.model_rebuild()
