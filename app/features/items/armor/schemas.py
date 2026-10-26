"""Armor write schemas: ``POST /items/armor`` and ``PATCH /items/{id}/armor``."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.constants import ArmorProficiency
from app.features.items.crud.schemas import ItemCoreCreate

ArmorClass = Annotated[int, Field(ge=0, le=100)]
MaxDexBonus = Annotated[int, Field(ge=0, le=20)]
StrengthRequirement = Annotated[int, Field(ge=0, le=30)]


class ArmorDetailsIn(BaseModel):
    """
    An armor's stats. ``armor_category=SHIELD`` makes it a shield: ``armor_class_base`` is then the bonus it
    adds. ``armor_class_max_dex_bonus`` — the DEX cap of MEDIUM armor (2 when unset).
    """

    model_config = ConfigDict(extra="forbid")

    armor_category: ArmorProficiency | None = None
    armor_class_base: ArmorClass | None = None
    armor_class_max_dex_bonus: MaxDexBonus | None = None
    strength_requirement: StrengthRequirement | None = None
    stealth_disadvantage: bool = False


class ArmorCreate(ItemCoreCreate):
    """A new armor or shield: the core and its stats (``armor``)."""

    armor: ArmorDetailsIn = ArmorDetailsIn()


class ArmorUpdate(ArmorDetailsIn):
    """PATCH an armor's stats (only the fields sent change; ``stealth_disadvantage`` can't be null)."""
