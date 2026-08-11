"""Request/response schemas for the item endpoints."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import DamageType, DiceType, ItemRarity, ItemType


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
    is_homebrew: bool = False


class ItemCreate(ItemBase):
    """Payload for creating an item (GM only)."""


class ItemUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    item_type: ItemType | None = None
    rarity: ItemRarity | None = None
    requires_attunement: bool | None = None
    weight: Decimal | None = None
    cost_gold: Decimal | None = None
    damage_dice_count: int | None = None
    damage_dice_type: DiceType | None = None
    damage_type: DamageType | None = None
    weapon_properties: str | None = None
    armor_class_base: int | None = None
    armor_class_dex_bonus: bool | None = None
    armor_class_max_dex_bonus: int | None = None
    strength_requirement: int | None = None
    stealth_disadvantage: bool | None = None
    description: str | None = None
    is_homebrew: bool | None = None


class ItemResponse(ItemBase):
    """Full item representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None


class ItemGetAllResponse(BaseModel):
    """Lightweight listing row: no description, weapon/armor detail fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    item_type: ItemType
    rarity: ItemRarity
    cost_gold: Decimal | None = None
    is_homebrew: bool


class SourceItemEntry(BaseModel):
    """One starting-equipment entry: a reference item plus a quantity."""

    item_id: int
    quantity: int = Field(default=1, ge=0)


def _validate_unique_item_ids(entries: list[SourceItemEntry]) -> list[SourceItemEntry]:
    item_ids = [entry.item_id for entry in entries]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Duplicate item IDs are not allowed.")

    return entries


class SourceItemsUpdate(BaseModel):
    """Full replacement list of starting items for a class or background."""

    items: list[SourceItemEntry]

    @field_validator("items")
    def validate_unique_item_ids(cls, items):
        """Reject lists containing duplicate item IDs."""
        return _validate_unique_item_ids(items)


class ItemBriefResponse(BaseModel):
    """Compact item representation embedded in source-item listings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    item_type: ItemType


class SourceItemResponse(BaseModel):
    """A starting-equipment entry as returned by ``GET /{source}/{id}/items``."""

    model_config = ConfigDict(from_attributes=True)

    item_id: int
    quantity: int
    item: ItemBriefResponse
