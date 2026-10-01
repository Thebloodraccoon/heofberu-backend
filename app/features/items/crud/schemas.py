"""Request/response schemas for the item endpoints."""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.constants import DamageType, DiceType, ItemRarity, ItemType

# Input bounds follow the column sizes (``Numeric(6, 2)`` weight, ``Numeric(10, 2)`` cost, ``String(200)`` name,
# ``String(300)`` properties); responses stay unconstrained so legacy rows always serialize.
ItemName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Weight = Annotated[Decimal, Field(ge=0, max_digits=6, decimal_places=2)]
CostGold = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
DiceCount = Annotated[int, Field(ge=1, le=100)]
ArmorClass = Annotated[int, Field(ge=0, le=100)]
MaxDexBonus = Annotated[int, Field(ge=0, le=20)]
StrengthRequirement = Annotated[int, Field(ge=0, le=30)]
WeaponProperties = Annotated[str, StringConstraints(max_length=300)]

_NOT_NULL_FIELDS = (
    "name",
    "item_type",
    "rarity",
    "requires_attunement",
    "armor_class_dex_bonus",
    "stealth_disadvantage",
    "description",
)


class ItemBase(BaseModel):
    """Base item fields, including weapon- and armor-specific attributes."""

    name: str
    item_type: ItemType
    rarity: ItemRarity = ItemRarity.NONE
    requires_attunement: bool = False

    weight: Decimal | None = None  # in pounds
    cost_gold: Decimal | None = None

    # Weapon-specific (relevant when item_type == WEAPON)
    damage_dice_count: int | None = None  # e.g. 2
    damage_dice_type: DiceType | None = None  # e.g. D6 -> "2d6" combined
    damage_type: DamageType | None = None
    weapon_properties: str | None = None  # e.g. "FINESSE,LIGHT,THROWN"

    # Armor-specific (relevant when item_type in (ARMOR, SHIELD))
    armor_class_base: int | None = None
    armor_class_dex_bonus: bool = True
    armor_class_max_dex_bonus: int | None = None
    strength_requirement: int | None = None
    stealth_disadvantage: bool = False

    description: str = ""


class ItemCreate(ItemBase):
    """Payload for creating an item (GM only)."""

    name: ItemName
    weight: Weight | None = None
    cost_gold: CostGold | None = None
    damage_dice_count: DiceCount | None = None
    weapon_properties: WeaponProperties | None = None
    armor_class_base: ArmorClass | None = None
    armor_class_max_dex_bonus: MaxDexBonus | None = None
    strength_requirement: StrengthRequirement | None = None


class ItemUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    An explicit ``null`` is rejected for the NOT NULL columns; the nullable
    weapon/armor/price fields can be cleared with ``null``.
    """

    name: ItemName | None = None
    item_type: ItemType | None = None
    rarity: ItemRarity | None = None
    requires_attunement: bool | None = None
    weight: Weight | None = None
    cost_gold: CostGold | None = None
    damage_dice_count: DiceCount | None = None
    damage_dice_type: DiceType | None = None
    damage_type: DamageType | None = None
    weapon_properties: WeaponProperties | None = None
    armor_class_base: ArmorClass | None = None
    armor_class_dex_bonus: bool | None = None
    armor_class_max_dex_bonus: MaxDexBonus | None = None
    strength_requirement: StrengthRequirement | None = None
    stealth_disadvantage: bool | None = None
    description: str | None = None

    @field_validator(*_NOT_NULL_FIELDS)
    @classmethod
    def reject_explicit_null(cls, value):
        """These fields map to NOT NULL columns: omit them to leave them unchanged."""

        if value is None:
            raise ValueError("This field cannot be null; omit it to leave it unchanged.")

        return value


class ItemResponse(ItemBase):
    """Full item representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class ItemGetAllResponse(BaseModel):
    """Lightweight listing row: no description, weapon/armor detail fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    item_type: ItemType
    rarity: ItemRarity
    cost_gold: Decimal | None = None
