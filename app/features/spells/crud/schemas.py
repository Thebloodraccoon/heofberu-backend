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
    """Reject duplicate spell components."""

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
    """Create payload for a spell; empty availability lists mean unrestricted."""

    available_classes: list[int] | None = None
    available_subclasses: list[int] | None = None
    available_races: list[int] | None = None
    available_subraces: list[int] | None = None


class SpellUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics). Availability excluded."""

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
        """Reject duplicate spell components, skipping the ``None`` PATCH case."""

        if value is None:
            return value

        return _validate_unique_components(value)


class ClassBriefResponse(BaseModel):
    """Minimal class info, embedded in SpellResponse.available_classes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SubclassBriefResponse(BaseModel):
    """Minimal subclass info, embedded in SpellResponse.available_subclasses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class RaceBriefResponse(BaseModel):
    """Minimal race info, embedded in SpellResponse.available_races."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SubraceBriefResponse(BaseModel):
    """Minimal subrace info, embedded in SpellResponse.available_subraces."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SpellResponse(SpellBase):
    """Full spell representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    available_classes: list[ClassBriefResponse] = []
    available_subclasses: list[SubclassBriefResponse] = []
    available_races: list[RaceBriefResponse] = []
    available_subraces: list[SubraceBriefResponse] = []


class SpellGetAllResponse(BaseModel):
    """Lightweight listing row, including availability summaries but no heavy detail fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    school: SpellSchool
    level: SpellLevel
    available_classes: list[ClassBriefResponse] = []
    available_subclasses: list[SubclassBriefResponse] = []
    available_races: list[RaceBriefResponse] = []
    available_subraces: list[SubraceBriefResponse] = []
