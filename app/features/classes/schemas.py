"""Request/response schemas for the class endpoints (class-level only; see subclasses/crud/schemas.py)."""

import math

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore, ArmorProficiency, DiceType, SpellLevel, WeaponProficiency
from app.features.classes.subclasses.crud.schemas import SubclassBriefResponse
from app.features.shared.features.schemas import NestedFeatureResponse
from app.features.shared.items.schemas import SourceItemResponse


def _proficiency_bonus(class_level: int) -> int:
    """Return the proficiency bonus for a given class level (1-20)."""

    return math.ceil(class_level / 4) + 1


def _validate_unique_saving_throws(saving_throws: list[AbilityScore]) -> list[AbilityScore]:
    if len(saving_throws) != len(set(saving_throws)):
        raise ValueError("Duplicate saving throws are not allowed.")

    return saving_throws


def _validate_unique_armor_proficiencies(armor_proficiencies: list[ArmorProficiency]) -> list[ArmorProficiency]:
    if len(armor_proficiencies) != len(set(armor_proficiencies)):
        raise ValueError("Duplicate armor proficiencies are not allowed.")

    return armor_proficiencies


def _validate_unique_weapon_proficiencies(weapon_proficiencies: list[WeaponProficiency]) -> list[WeaponProficiency]:
    if len(weapon_proficiencies) != len(set(weapon_proficiencies)):
        raise ValueError("Duplicate weapon proficiencies are not allowed.")

    return weapon_proficiencies


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


class ClassBase(BaseModel):
    """Base class fields shared by create, update, and response schemas."""

    name: str
    hit_dice: DiceType
    skill_choice_count: int = 2
    spellcasting_ability: AbilityScore | None
    description: str = ""


class ClassCreate(ClassBase):
    """
    Create payload for a class.

    Kept minimal on purpose: only the class's own scalar fields plus its
    directly-owned simple child rows (``saving_throws``,
    ``armor_proficiencies``, ``weapon_proficiencies``,
    ``available_skills``) are set here, atomically, alongside the ``Class``
    row itself.

    Everything with heavier/nested dependencies — ``features``,
    ``subclasses`` (which themselves nest features), ``starting_items``,
    and ``spell_slot_progression`` — is intentionally NOT part of create.
    Attach those afterwards through their dedicated endpoints:
      - ``POST /classes/{id}/features``
      - ``POST /classes/{id}/subclasses``
      - ``PUT /classes/{id}/starting-items``
      - ``PUT /classes/{id}/spell-slots/{class_level}``
    """

    saving_throws: list[AbilityScore] = []
    armor_proficiencies: list[ArmorProficiency] = []
    weapon_proficiencies: list[WeaponProficiency] = []
    available_skills: list[int] | None = None

    @field_validator("saving_throws")
    def validate_unique_saving_throws(cls, v):
        return _validate_unique_saving_throws(v)

    @field_validator("armor_proficiencies")
    def validate_unique_armor_proficiencies(cls, v):
        return _validate_unique_armor_proficiencies(v)

    @field_validator("weapon_proficiencies")
    def validate_unique_weapon_proficiencies(cls, v):
        return _validate_unique_weapon_proficiencies(v)

    @field_validator("available_skills")
    def validate_unique_available_skills(cls, v):
        if v is None:
            return v

        return _validate_unique_skill_ids(v)


class ClassUpdate(BaseModel):
    """
    All fields optional — PATCH semantics.

    Does not include ``available_skills`` (dedicated PUT endpoint).
    Does not include ``features`` or ``subclasses`` — manage those through
    their own endpoints to keep replace-vs-patch semantics unambiguous.
    ``saving_throws``, ``armor_proficiencies`` and ``weapon_proficiencies``
    are full-replace when set.
    """

    name: str | None = None
    hit_dice: DiceType | None = None
    skill_choice_count: int | None = None
    spellcasting_ability: AbilityScore | None = None
    description: str | None = None
    saving_throws: list[AbilityScore] | None = None
    armor_proficiencies: list[ArmorProficiency] | None = None
    weapon_proficiencies: list[WeaponProficiency] | None = None

    @field_validator("saving_throws")
    def validate_unique_saving_throws_update(cls, v):
        if v is None:
            return v

        return _validate_unique_saving_throws(v)

    @field_validator("armor_proficiencies")
    def validate_unique_armor_proficiencies_update(cls, v):
        if v is None:
            return v

        return _validate_unique_armor_proficiencies(v)

    @field_validator("weapon_proficiencies")
    def validate_unique_weapon_proficiencies_update(cls, v):
        if v is None:
            return v

        return _validate_unique_weapon_proficiencies(v)


class SavingThrowsUpdate(BaseModel):
    """Full replacement list of saving throw proficiencies for a class."""

    saving_throws: list[AbilityScore]

    @field_validator("saving_throws")
    def validate_unique(cls, v):
        return _validate_unique_saving_throws(v)


class ArmorProficienciesUpdate(BaseModel):
    """Full replacement list of armor proficiencies for a class."""

    armor_proficiencies: list[ArmorProficiency]

    @field_validator("armor_proficiencies")
    def validate_unique(cls, v):
        return _validate_unique_armor_proficiencies(v)


class WeaponProficienciesUpdate(BaseModel):
    """Full replacement list of weapon proficiencies for a class."""

    weapon_proficiencies: list[WeaponProficiency]

    @field_validator("weapon_proficiencies")
    def validate_unique(cls, v):
        return _validate_unique_weapon_proficiencies(v)


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
    spell_slot_progression: list[SpellSlotProgressionResponse] = []
    subclasses: list[SubclassBriefResponse] = []


class ClassGetAllResponse(BaseModel):
    """Lightweight listing row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hit_dice: DiceType
    subclasses: list["SubclassListResponse"] = []


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


class ClassFullResponse(ClassResponse):
    """
    Everything about a class in one payload: base fields,
    saving throws/armor proficiencies/available skills/starting
    items/spell slots (all inherited from ``ClassResponse``), plus
    CLASS-source ``features`` and a brief reference to each subclass
    (``SubclassBriefResponse``). The full per-subclass picture (its own
    SUBCLASS-source features) lives on ``GET /classes/{class_id}/subclasses/{subclass_id}``.

    Returned by ``GET /classes/{id}`` and cached as a single unit under
    the ``classes`` namespace, so a client that needs the class (features,
    items, slots) gets it in one cached round-trip instead of stitching
    together several endpoints.
    """

    features: list[NestedFeatureResponse] = []
    subclasses: list[SubclassBriefResponse] = []


# Needed because ClassGetAllResponse references SubclassListResponse by
# forward ref (defined in subclasses/crud/schemas.py) to avoid a circular
# import at module load time (subclasses/crud/schemas.py does not import
# from here).
from app.features.classes.subclasses.crud.schemas import SubclassListResponse  # noqa: E402

ClassGetAllResponse.model_rebuild()
