"""ORM model for the reference table of equipment and magic items."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import DamageType, DiceType, ItemRarity, ItemType
from app.models.enums import DamageTypeType, DiceTypeColumn, ItemRarityType, ItemTypeType
from app.settings.base import Base


class Item(Base):
    """
    Reference table of equipment/items (weapons, armor, gear, magic
    items), shared across all characters. GM-managed, like Race and Spell.
    """

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    item_type: Mapped[ItemType] = mapped_column(ItemTypeType)
    rarity: Mapped[ItemRarity] = mapped_column(ItemRarityType, default="NONE")
    requires_attunement: Mapped[bool] = mapped_column(default=False)

    weight: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # in pounds
    cost_gold: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    # Weapon-specific (nullable when not applicable)
    damage_dice_count: Mapped[int | None] = mapped_column()  # e.g. 2
    damage_dice_type: Mapped[DiceType | None] = mapped_column(DiceTypeColumn)  # e.g. D6 -> "2d6" combined
    damage_type: Mapped[DamageType | None] = mapped_column(DamageTypeType)
    weapon_properties: Mapped[str | None] = mapped_column(String(300))  # e.g. "FINESSE,LIGHT,THROWN"

    # Armor-specific (nullable when not applicable)
    armor_class_base: Mapped[int | None] = mapped_column()
    armor_class_dex_bonus: Mapped[bool] = mapped_column(default=True)
    armor_class_max_dex_bonus: Mapped[int | None] = mapped_column()
    strength_requirement: Mapped[int | None] = mapped_column()
    stealth_disadvantage: Mapped[bool] = mapped_column(default=False)

    description: Mapped[str] = mapped_column(Text, default="")

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, name='{self.name}', item_type='{self.item_type}')>"
