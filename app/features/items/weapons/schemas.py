"""Weapon write schemas: ``POST /items/weapons`` and ``PATCH /items/{id}/weapon``."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import AttackType, DamageType, DiceType, WeaponProficiency
from app.core.types import EntityId
from app.features.items.crud.schemas import ItemCoreCreate

DiceCount = Annotated[int, Field(ge=1, le=100)]
RangeFeet = Annotated[int, Field(ge=1, le=10_000)]
MAX_PROPERTIES = 20


def _unique_ids(ids: list[int] | None) -> list[int] | None:
    """A property list is a set: repeats are dropped, order kept."""

    return list(dict.fromkeys(ids)) if ids is not None else None


class WeaponDetailsIn(BaseModel):
    """
    A weapon's stats (every field optional; ``null`` clears it on a PATCH). ``range_*`` — for Thrown /
    Ammunition weapons, ``versatile_dice_*`` — the two-handed damage of a Versatile one.
    """

    model_config = ConfigDict(extra="forbid")

    weapon_category: WeaponProficiency | None = None
    attack_type: AttackType | None = None
    damage_dice_count: DiceCount | None = None
    damage_dice_type: DiceType | None = None
    damage_type: DamageType | None = None
    range_normal: RangeFeet | None = None
    range_long: RangeFeet | None = None
    versatile_dice_count: DiceCount | None = None
    versatile_dice_type: DiceType | None = None


class WeaponCreate(ItemCoreCreate):
    """A new weapon: the core, its stats (``weapon``) and its properties (``property_ids``, ``/items/properties``)."""

    weapon: WeaponDetailsIn = WeaponDetailsIn()
    property_ids: list[EntityId] = Field([], max_length=MAX_PROPERTIES)

    _dedupe = field_validator("property_ids")(_unique_ids)


class WeaponUpdate(WeaponDetailsIn):
    """PATCH a weapon's stats (only the fields sent change); ``property_ids`` replaces the whole property list."""

    property_ids: list[EntityId] | None = Field(None, max_length=MAX_PROPERTIES)

    _dedupe = field_validator("property_ids")(_unique_ids)

    @field_validator("property_ids")
    @classmethod
    def _no_null_properties(cls, value):
        """Send ``[]`` to clear the properties; omit the field to keep them."""

        if value is None:
            raise ValueError("property_ids cannot be null; send [] to clear or omit it.")
        return value
