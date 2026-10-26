"""Armor service: an armor's (or a shield's) stats."""

from typing import Any

from pydantic import BaseModel

from app.constants import ItemKind
from app.features.items.crud.kinds import KindItemService
from app.features.items.exceptions import InvalidItemDataError
from app.models.items.item_model import Item, ItemArmorDetails


def check_armor(details: dict[str, Any]) -> None:
    """422 when an armor (or a shield) has a category but no ``armor_class_base`` — the AC math needs it. Pure."""

    if details.get("armor_category") is not None and details.get("armor_class_base") is None:
        raise InvalidItemDataError("armor_category requires armor_class_base (a shield's bonus for SHIELD).")


class ArmorService(KindItemService):
    """Armor and shields: stats in ``item_armor_details``; a categorised armor must carry its AC base."""

    kind = ItemKind.ARMOR
    detail_attr = "armor"
    detail_model = ItemArmorDetails

    async def _check(self, details: dict[str, Any], data: BaseModel, *, item: Item | None, touched: set[str]) -> None:
        check_armor(details)
