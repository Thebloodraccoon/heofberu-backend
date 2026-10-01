"""Request/response schemas for the spell endpoints."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
from app.core.types import EntityId

_NAME_MAX_LENGTH = 300
_TEXT_MAX_LENGTH = 20_000
_MAX_AVAILABILITY_IDS = 500

# Spell fields that map to NOT NULL columns: an explicit ``null`` in a PATCH is rejected.
_NON_NULLABLE_UPDATE_FIELDS = (
    "name",
    "school",
    "level",
    "cast_time",
    "range_type",
    "components",
    "is_material_consumed",
    "is_ritual",
    "duration",
    "is_concentration",
    "description",
)

SpellName = Annotated[str, Field(min_length=1, max_length=_NAME_MAX_LENGTH)]
SpellText = Annotated[str, Field(max_length=_TEXT_MAX_LENGTH)]
DiceCount = Annotated[int, Field(ge=1, le=100)]
RangeValue = Annotated[int, Field(ge=0, le=1_000_000)]
AvailabilityIds = Annotated[list[EntityId], Field(max_length=_MAX_AVAILABILITY_IDS)]


def dedupe_ids(values: list[int] | None) -> list[int] | None:
    """Collapse repeated ids (a set of ids is what the caller means), keeping the first-seen order."""

    return None if values is None else list(dict.fromkeys(values))


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
    """
    Create payload for a spell; empty availability lists mean unrestricted.

    Write-side rules on top of :class:`SpellBase`: bounded names/texts/numbers,
    dice count and type given together, the material description and
    "consumed" flag only with a ``MATERIAL`` component, unknown keys rejected.
    """

    model_config = ConfigDict(extra="forbid")

    name: SpellName
    range_value: RangeValue | None = None
    material: SpellText | None = None
    damage_dice_count: DiceCount | None = None
    healing_dice_count: DiceCount | None = None
    description: SpellText
    higher_levels: SpellText | None = None

    available_classes: AvailabilityIds | None = None
    available_subclasses: AvailabilityIds | None = None
    available_races: AvailabilityIds | None = None
    available_subraces: AvailabilityIds | None = None

    @field_validator("available_classes", "available_subclasses", "available_races", "available_subraces", mode="after")
    @classmethod
    def dedupe_availability_ids(cls, value):
        """Repeated ids collapse to one (the association's primary key forbids duplicates)."""

        return dedupe_ids(value)

    @model_validator(mode="after")
    def validate_cross_field_rules(self):
        """Dice count/type are given together; material text and consumption need a MATERIAL component."""

        for prefix in ("damage", "healing"):
            if (getattr(self, f"{prefix}_dice_count") is None) != (getattr(self, f"{prefix}_dice_type") is None):
                raise ValueError(f"{prefix}_dice_count and {prefix}_dice_type must be set together.")

        if (self.material or self.is_material_consumed) and Component.MATERIAL not in self.components:
            raise ValueError("material and is_material_consumed require the MATERIAL component.")

        return self


class SpellUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics). Availability excluded."""

    model_config = ConfigDict(extra="forbid")

    name: SpellName | None = None
    school: SpellSchool | None = None
    level: SpellLevel | None = None
    cast_time: SpellCastTime | None = None
    range_type: SpellRangeType | None = None
    range_value: RangeValue | None = None
    components: list[Component] | None = None
    is_material_consumed: bool | None = None
    material: SpellText | None = None
    is_ritual: bool | None = None
    duration: SpellDuration | None = None
    is_concentration: bool | None = None
    attack_type: AttackType | None = None
    save_stat: AbilityScore | None = None
    damage_type: DamageType | None = None
    damage_dice_count: DiceCount | None = None
    damage_dice_type: DiceType | None = None
    healing_target: HealingTarget | None = None
    healing_dice_count: DiceCount | None = None
    healing_dice_type: DiceType | None = None
    description: SpellText | None = None
    higher_levels: SpellText | None = None

    @field_validator("components")
    def validate_unique_components(cls, value):
        """Reject duplicate spell components, skipping the ``None`` PATCH case."""

        if value is None:
            return value

        return _validate_unique_components(value)

    @model_validator(mode="after")
    def reject_null_for_required_fields(self):
        """An explicit ``null`` would clear a NOT NULL column; omit the field instead."""

        nulled = [
            name
            for name in _NON_NULLABLE_UPDATE_FIELDS
            if name in self.model_fields_set and getattr(self, name) is None
        ]
        if nulled:
            raise ValueError(f"{', '.join(nulled)} cannot be null.")

        return self


class NamedRef(BaseModel):
    """Minimal ``{id, name}`` of a class/subclass/race/subrace, embedded in a spell's availability lists."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SpellResponse(SpellBase):
    """Full spell representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    available_classes: list[NamedRef] = []
    available_subclasses: list[NamedRef] = []
    available_races: list[NamedRef] = []
    available_subraces: list[NamedRef] = []


class SpellGetAllResponse(BaseModel):
    """Lightweight listing row, including availability summaries but no heavy detail fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    school: SpellSchool
    level: SpellLevel
    available_classes: list[NamedRef] = []
    available_subclasses: list[NamedRef] = []
    available_races: list[NamedRef] = []
    available_subraces: list[NamedRef] = []
