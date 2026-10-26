"""Item schemas: the core every item has, the per-kind detail views, and the core / gear writes."""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.constants import (
    ArmorProficiency,
    AttackType,
    DamageType,
    DiceType,
    GearType,
    ItemKind,
    ItemRarity,
    ToolCategory,
    WeaponProficiency,
)
from app.features.features.effects.schemas import EffectGroup

# Input bounds follow the column sizes (``Numeric(6, 2)`` weight, ``Numeric(10, 2)`` cost, ``String(200)`` name);
# responses stay unconstrained so legacy rows always serialize.
ItemName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Weight = Annotated[Decimal, Field(ge=0, max_digits=6, decimal_places=2)]
CostGold = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
MagicBonus = Annotated[int, Field(ge=-10, le=10)]

# The core columns a kind's create payload shares (``ItemCoreCreate``).
CORE_FIELDS = ("name", "rarity", "requires_attunement", "weight", "cost_gold", "magic_bonus", "description")


def reject_explicit_null(names: tuple[str, ...]):
    """A ``field_validator`` rejecting an explicit ``null`` for NOT NULL columns of a PATCH payload."""

    def check(cls, value):
        if value is None:
            raise ValueError("This field cannot be null; omit it to leave it unchanged.")
        return value

    return field_validator(*names)(check)


class WeaponPropertyBrief(BaseModel):
    """A weapon property as embedded in an item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class WeaponDetailsResponse(BaseModel):
    """The weapon stats of a ``WEAPON`` item."""

    model_config = ConfigDict(from_attributes=True)

    weapon_category: WeaponProficiency | None = None
    attack_type: AttackType | None = None
    damage_dice_count: int | None = None
    damage_dice_type: DiceType | None = None
    damage_type: DamageType | None = None
    range_normal: int | None = None
    range_long: int | None = None
    versatile_dice_count: int | None = None
    versatile_dice_type: DiceType | None = None


class ArmorDetailsResponse(BaseModel):
    """The armor stats of an ``ARMOR`` item (``armor_class_base`` of a shield is its bonus)."""

    model_config = ConfigDict(from_attributes=True)

    armor_category: ArmorProficiency | None = None
    armor_class_base: int | None = None
    armor_class_max_dex_bonus: int | None = None
    strength_requirement: int | None = None
    stealth_disadvantage: bool = False


class ToolDetailsResponse(BaseModel):
    """The tool facts of a ``TOOL`` item."""

    model_config = ConfigDict(from_attributes=True)

    tool_category: ToolCategory | None = None


class ItemResponse(BaseModel):
    """
    Full item: the core, the detail record of its ``kind`` (``weapon`` / ``armor`` / ``tool``, the others
    ``null``; a ``GEAR`` item has none but its ``subtype``), the weapon ``properties`` and the speed/AC
    ``effects`` it gives while equipped (non-empty effect groups only).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: ItemKind
    subtype: GearType | None = None
    rarity: ItemRarity = ItemRarity.NONE
    requires_attunement: bool = False
    weight: Decimal | None = None  # in pounds
    cost_gold: Decimal | None = None
    # +N of magic armor/shields (to AC) and weapons (to attack and damage)
    magic_bonus: int | None = None
    description: str = ""
    weapon: WeaponDetailsResponse | None = None
    armor: ArmorDetailsResponse | None = None
    tool: ToolDetailsResponse | None = None
    properties: list[WeaponPropertyBrief] = []
    effects: list[EffectGroup] = []


class ItemGetAllResponse(BaseModel):
    """Lightweight listing row: no description or stats, but the kind, subtype and category."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: ItemKind
    subtype: GearType | None = None
    rarity: ItemRarity
    cost_gold: Decimal | None = None
    weapon_category: WeaponProficiency | None = None
    armor_category: ArmorProficiency | None = None
    tool_category: ToolCategory | None = None


class ItemCoreCreate(BaseModel):
    """The core fields of any create payload (the kind comes from the endpoint)."""

    model_config = ConfigDict(extra="forbid")

    name: ItemName
    rarity: ItemRarity = ItemRarity.NONE
    requires_attunement: bool = False
    weight: Weight | None = None
    cost_gold: CostGold | None = None
    magic_bonus: MagicBonus | None = None
    description: str = ""


class GearCreate(ItemCoreCreate):
    """``POST /items``: a ``GEAR`` item — anything that isn't a weapon, armor or tool — and what it is."""

    subtype: GearType = GearType.OTHER


class ItemCoreUpdate(BaseModel):
    """
    ``PATCH /items/{id}``: core fields only (PATCH semantics). ``kind`` is fixed at creation; ``subtype`` is
    for a ``GEAR`` item only (422 otherwise); the kind's stats have their own endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    name: ItemName | None = None
    subtype: GearType | None = None
    rarity: ItemRarity | None = None
    requires_attunement: bool | None = None
    weight: Weight | None = None
    cost_gold: CostGold | None = None
    magic_bonus: MagicBonus | None = None
    description: str | None = None

    _no_nulls = reject_explicit_null(("name", "subtype", "rarity", "requires_attunement", "description"))
