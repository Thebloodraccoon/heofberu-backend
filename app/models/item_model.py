"""ORM model for the reference table of equipment and magic items."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.models.enums import DamageTypeType, DiceTypeColumn, ItemRarityType, ItemTypeType
from app.settings import settings


class Item(settings.Base):  # type: ignore
    """
    Reference table of equipment/items (weapons, armor, gear, magic
    items), shared across all characters. GM-managed, like Race and Spell.
    """

    __tablename__ = "items"

    id = Column(Integer, primary_key=True)

    name = Column(String(200), nullable=False, unique=True, index=True)
    item_type = Column(ItemTypeType, nullable=False)
    rarity = Column(ItemRarityType, nullable=False, default="NONE")
    requires_attunement = Column(Boolean, nullable=False, default=False)

    weight = Column(Numeric(6, 2), nullable=True)  # in pounds
    cost_gold = Column(Numeric(10, 2), nullable=True)

    # Weapon-specific (nullable when not applicable)
    damage_dice_count = Column(Integer, nullable=True)  # e.g. 2
    damage_dice_type = Column(DiceTypeColumn, nullable=True)  # e.g. D6 -> "2d6" combined
    damage_type = Column(DamageTypeType, nullable=True)
    weapon_properties = Column(String(300), nullable=True)  # e.g. "FINESSE,LIGHT,THROWN"

    # Armor-specific (nullable when not applicable)
    armor_class_base = Column(Integer, nullable=True)
    armor_class_dex_bonus = Column(Boolean, nullable=False, default=True)
    armor_class_max_dex_bonus = Column(Integer, nullable=True)
    strength_requirement = Column(Integer, nullable=True)
    stealth_disadvantage = Column(Boolean, nullable=False, default=False)

    description = Column(Text, nullable=False, default="")
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    created_by = relationship("User")

    def __repr__(self):
        return f"<Item(id={self.id}, name='{self.name}', item_type='{self.item_type}')>"
