"""ORM model for the GM-managed dictionary of weapon properties and its item link table."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Table, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.settings.base import Base

# Which properties a weapon has (any number, e.g. Finesse + Light + Thrown).
item_weapon_properties = Table(
    "item_weapon_properties",
    Base.metadata,
    Column("item_id", Integer, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("property_id", Integer, ForeignKey("weapon_properties.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK leads with item_id; the property filter and the delete guard look up by property.
    Index("ix_item_weapon_properties_property_id", "property_id"),
)


class WeaponProperty(Base):
    """
    A weapon property (Finesse, Light, Thrown, homebrew ones...) — a
    dictionary the GM extends, like tags. The flags say which item fields a
    weapon with the property must fill: ``requires_range`` (Thrown,
    Ammunition — ``range_normal``), ``requires_versatile_damage`` (Versatile
    — ``versatile_dice_*``).
    """

    __tablename__ = "weapon_properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    requires_range: Mapped[bool] = mapped_column(default=False, server_default=false())
    requires_versatile_damage: Mapped[bool] = mapped_column(default=False, server_default=false())

    def __repr__(self) -> str:
        return f"<WeaponProperty(id={self.id}, name='{self.name}')>"
