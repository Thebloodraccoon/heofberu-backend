"""Request/response schemas for the spell endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import (
    AbilityScore,
    AttackType,
    Component,
    DamageType,
    DiceType,
    HealingTarget,
    SpellCastTime,
    SpellDuration,
    SpellLevel,
    SpellRangeType,
    SpellSchool,
)


def _validate_unique_components(components: list[Component]) -> list[Component]:
    if len(components) != len(set(components)):
        raise ValueError("Duplicate spell component(s) are not allowed.")

    return components


class SpellBase(BaseModel):
    """Base spell fields shared by create and response schemas."""

    name: str
    school: SpellSchool
    level: SpellLevel

    cast_time: SpellCastTime
    range_type: SpellRangeType
    range_value: int | None = None

    components: list[Component] = []
    is_material_consumed: bool = False
    material: str | None = None  # material component description, relevant when Component.MATERIAL is in `components`

    is_ritual: bool = False

    duration: SpellDuration
    is_concentration: bool = False

    # None means the spell has no attack roll (e.g. a save-based or utility spell).
    attack_type: AttackType | None = None
    save_stat: AbilityScore | None = None
    damage_type: DamageType | None = None
    damage_dice_count: int | None = None  # e.g. 2
    damage_dice_type: DiceType | None = None  # e.g. D6 -> "2d6" combined

    # None means the spell doesn't heal.
    healing_target: HealingTarget | None = None
    healing_dice_count: int | None = None
    healing_dice_type: DiceType | None = None

    description: str
    higher_levels: str | None = None

    @field_validator("components")
    def validate_unique_components(cls, value):
        """Reject duplicate spell components."""
        return _validate_unique_components(value)


class SpellCreate(SpellBase):
    """
    Create payload for a spell.

    ``available_classes`` / ``available_races`` are optional. If omitted
    (or left empty), the spell is unrestricted — available to every class
    and race. If provided, they're saved together with the spell in a
    single transaction, matching how ``RaceCreate`` handles ability bonuses
    and granted skills.
    """

    available_classes: list[int] | None = None
    available_races: list[int] | None = None


class SpellUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Deliberately does NOT include available_classes/available_races: those
    keep their own PUT endpoints with explicit full-replace semantics, same
    reasoning as Race's ability-bonuses/granted-skills split.
    """

    name: str | None = None
    school: SpellSchool | None = None
    level: SpellLevel | None = None
    cast_time: SpellCastTime | None = None
    range_type: SpellRangeType | None = None
    range_value: int | None = None
    components: list[Component] | None = None
    is_material_consumed: bool | None = None
    material: str | None = None
    is_ritual: bool | None = None
    duration: SpellDuration | None = None
    is_concentration: bool | None = None
    attack_type: AttackType | None = None
    save_stat: AbilityScore | None = None
    damage_type: DamageType | None = None
    damage_dice_count: int | None = None
    damage_dice_type: DiceType | None = None
    healing_target: HealingTarget | None = None
    healing_dice_count: int | None = None
    healing_dice_type: DiceType | None = None
    description: str | None = None
    higher_levels: str | None = None

    @field_validator("components")
    def validate_unique_components(cls, value):
        """Reject duplicate spell components (skipping the ``None`` PATCH case)."""
        if value is None:
            return value
        return _validate_unique_components(value)


class ClassAvailabilityUpdate(BaseModel):
    """Full replacement list of class IDs a spell is available to. Empty = unrestricted."""

    class_ids: list[int]


class RaceAvailabilityUpdate(BaseModel):
    """Full replacement list of race IDs a spell is available to. Empty = unrestricted."""

    race_ids: list[int]


class ClassBriefResponse(BaseModel):
    """Minimal class info, embedded in SpellResponse.available_classes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class RaceBriefResponse(BaseModel):
    """Minimal race info, embedded in SpellResponse.available_races."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SpellResponse(SpellBase):
    """Full spell representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_homebrew: bool
    created_by_id: int | None = None
    available_classes: list[ClassBriefResponse] = []
    available_races: list[RaceBriefResponse] = []


class SpellGetAllResponse(BaseModel):
    """
    Lightweight listing row.

    Includes available_classes/available_races so listing/dropdown UI can
    filter or badge spells by availability without a follow-up call to
    `GET /spells/{spell_id}`. Still excludes components, description,
    dice, and other heavier detail fields.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    school: SpellSchool
    level: SpellLevel
    is_homebrew: bool
    available_classes: list[ClassBriefResponse] = []
    available_races: list[RaceBriefResponse] = []
