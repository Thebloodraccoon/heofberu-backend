"""ORM models for the reference table of items: the shared core and the per-kind detail records."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
from app.models.enums import (
    ArmorProficiencyType,
    AttackTypeType,
    DamageTypeType,
    DiceTypeColumn,
    GearTypeType,
    ItemKindType,
    ItemRarityType,
    ToolCategoryType,
    WeaponProficiencyType,
)
from app.models.features.feature_engine_models import ITEM_EFFECT_TYPES
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.features.feature_engine_models import FeatureArmorClassEffect, FeatureSpeedEffect
    from app.models.items.weapon_property_model import WeaponProperty


class Item(Base):
    """
    Reference table of items, shared across all characters. GM-managed, like Race and Spell.

    The core every item has: identity (the one ``id`` inventory, starting equipment, proficiency effects and
    picks point at), ``kind`` (fixed at creation — see ``ItemKind``), the ``GEAR`` ``subtype``, rarity,
    attunement, weight, cost, ``magic_bonus`` (the +N of magic armor/shields to AC and weapons to attack and
    damage) and description. Kind-specific stats live in one detail record per kind (``weapon`` / ``armor`` /
    ``tool``, LEFT OUTER JOINed into every item load); the read-through properties below expose the ones the rules read
    (``armor_category``, ``armor_class_base``…) as ``None`` on an item of another kind. A weapon's
    ``properties`` and the speed/AC ``effects`` an item gives while equipped hang off the core.
    """

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    kind: Mapped[ItemKind] = mapped_column(ItemKindType, index=True)
    subtype: Mapped[GearType | None] = mapped_column(GearTypeType, index=True)
    rarity: Mapped[ItemRarity] = mapped_column(ItemRarityType, default="NONE")
    requires_attunement: Mapped[bool] = mapped_column(default=False)

    weight: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # in pounds
    cost_gold: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    magic_bonus: Mapped[int | None] = mapped_column()

    description: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        CheckConstraint("kind = 'GEAR' OR subtype IS NULL", name="ck_items_subtype_gear_only"),
        CheckConstraint("magic_bonus IS NULL OR magic_bonus BETWEEN -10 AND 10", name="ck_items_magic_bonus"),
    )

    weapon: Mapped[ItemWeaponDetails | None] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True, lazy="joined"
    )
    armor: Mapped[ItemArmorDetails | None] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True, lazy="joined"
    )
    tool: Mapped[ItemToolDetails | None] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True, lazy="joined"
    )
    properties: Mapped[list[WeaponProperty]] = relationship(
        secondary="item_weapon_properties", order_by="WeaponProperty.name"
    )
    speed_effects: Mapped[list[FeatureSpeedEffect]] = relationship(
        back_populates="item",
        primaryjoin="Item.id == FeatureSpeedEffect.item_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    armor_class_effects: Mapped[list[FeatureArmorClassEffect]] = relationship(
        back_populates="item",
        primaryjoin="Item.id == FeatureArmorClassEffect.item_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Read-through of the detail fields the rules read (combat stats, picks, starting-equipment filters).
    @property
    def weapon_category(self) -> WeaponProficiency | None:
        return self.weapon.weapon_category if self.weapon is not None else None

    @property
    def armor_category(self) -> ArmorProficiency | None:
        return self.armor.armor_category if self.armor is not None else None

    @property
    def armor_class_base(self) -> int | None:
        return self.armor.armor_class_base if self.armor is not None else None

    @property
    def armor_class_max_dex_bonus(self) -> int | None:
        return self.armor.armor_class_max_dex_bonus if self.armor is not None else None

    @property
    def strength_requirement(self) -> int | None:
        return self.armor.strength_requirement if self.armor is not None else None

    @property
    def tool_category(self) -> ToolCategory | None:
        return self.tool.tool_category if self.tool is not None else None

    @property
    def effects(self) -> list[dict]:
        """The item's speed/AC effects as non-empty ``{effect_type, items}`` groups (relationships must be loaded)."""

        return [
            {"effect_type": effect_type, "items": items}
            for effect_type, attr in ITEM_EFFECT_TYPES
            if (items := getattr(self, attr))
        ]

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, name='{self.name}', kind='{self.kind}')>"


class ItemWeaponDetails(Base):
    """The weapon stats of a ``WEAPON`` item (one row per weapon)."""

    __tablename__ = "item_weapon_details"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    weapon_category: Mapped[WeaponProficiency | None] = mapped_column(WeaponProficiencyType, index=True)
    attack_type: Mapped[AttackType | None] = mapped_column(AttackTypeType)
    damage_dice_count: Mapped[int | None] = mapped_column()  # e.g. 2
    damage_dice_type: Mapped[DiceType | None] = mapped_column(DiceTypeColumn)  # e.g. D6 -> "2d6" combined
    damage_type: Mapped[DamageType | None] = mapped_column(DamageTypeType)
    # Normal / long range in feet (THROWN / AMMUNITION weapons).
    range_normal: Mapped[int | None] = mapped_column()
    range_long: Mapped[int | None] = mapped_column()
    # Two-handed damage of a VERSATILE weapon.
    versatile_dice_count: Mapped[int | None] = mapped_column()
    versatile_dice_type: Mapped[DiceType | None] = mapped_column(DiceTypeColumn)

    __table_args__ = (
        CheckConstraint(
            "range_normal IS NULL OR (range_normal > 0 AND (range_long IS NULL OR range_long >= range_normal))",
            name="ck_item_weapon_details_range",
        ),
        CheckConstraint(
            "(versatile_dice_count IS NULL) = (versatile_dice_type IS NULL)", name="ck_item_weapon_details_versatile"
        ),
    )

    item: Mapped[Item] = relationship(back_populates="weapon")


class ItemArmorDetails(Base):
    """The armor stats of an ``ARMOR`` item (a shield included: ``armor_category=SHIELD``)."""

    __tablename__ = "item_armor_details"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    armor_category: Mapped[ArmorProficiency | None] = mapped_column(ArmorProficiencyType, index=True)
    armor_class_base: Mapped[int | None] = mapped_column()  # a shield's bonus for SHIELD
    armor_class_max_dex_bonus: Mapped[int | None] = mapped_column()  # MEDIUM armor's DEX cap (2 when unset)
    strength_requirement: Mapped[int | None] = mapped_column()
    stealth_disadvantage: Mapped[bool] = mapped_column(default=False, server_default=false())

    item: Mapped[Item] = relationship(back_populates="armor")


class ItemToolDetails(Base):
    """The tool facts of a ``TOOL`` item."""

    __tablename__ = "item_tool_details"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    tool_category: Mapped[ToolCategory | None] = mapped_column(ToolCategoryType, index=True)

    item: Mapped[Item] = relationship(back_populates="tool")
