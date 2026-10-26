"""Weapon service: a weapon's stats and properties, and the rules between them."""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.constants import ItemKind
from app.core.base.service import BaseService
from app.features.items.crud.kinds import KindItemService
from app.features.items.exceptions import InvalidItemDataError
from app.models.items.item_model import Item, ItemWeaponDetails
from app.models.items.weapon_property_model import WeaponProperty

# Fields whose change re-checks what the weapon's properties require.
_PROPERTY_DEPENDENT_FIELDS = {
    "property_ids",
    "range_normal",
    "range_long",
    "versatile_dice_count",
    "versatile_dice_type",
}


def check_weapon(details: dict[str, Any], properties: Iterable[WeaponProperty], *, check_properties: bool) -> None:
    """
    422 when a weapon's stats don't fit together: a long range without a normal one (or shorter than it), a
    half-set two-handed damage, or — with ``check_properties`` — a property's required field missing
    (``requires_range`` → ``range_normal``, ``requires_versatile_damage`` → the two-handed damage). Pure.
    """

    normal, long = details.get("range_normal"), details.get("range_long")
    if long is not None and (normal is None or long < normal):
        raise InvalidItemDataError("range_long needs range_normal and must not be shorter than it.")
    if (details.get("versatile_dice_count") is None) != (details.get("versatile_dice_type") is None):
        raise InvalidItemDataError("Set both versatile_dice_count and versatile_dice_type, or neither.")

    if not check_properties:
        return
    properties = list(properties)
    needing_range = [prop.name for prop in properties if prop.requires_range]
    if needing_range and normal is None:
        raise InvalidItemDataError(f"Property {', '.join(needing_range)} requires range_normal.")
    needing_damage = [prop.name for prop in properties if prop.requires_versatile_damage]
    if needing_damage and details.get("versatile_dice_count") is None:
        raise InvalidItemDataError(f"Property {', '.join(needing_damage)} requires versatile_dice_count/_type.")


class WeaponService(KindItemService):
    """
    Weapons: stats in ``item_weapon_details``, properties in ``item_weapon_properties``. The property
    requirements are checked when a request touches the properties, the range or the two-handed damage, so
    editing a legacy weapon's damage without a range still works.
    """

    kind = ItemKind.WEAPON
    detail_attr = "weapon"
    detail_model = ItemWeaponDetails

    async def _properties(self, data: BaseModel, item: Item | None) -> list[WeaponProperty]:
        """The properties the weapon will have: the requested ones (400 on an unknown id) or its current ones."""

        if "property_ids" in data.model_fields_set or item is None:
            ids = getattr(data, "property_ids", None) or []
            return await BaseService.resolve_ids(self.repository.get_properties_by_ids, ids, "WeaponProperty")
        return list(item.properties)

    async def _check(self, details: dict[str, Any], data: BaseModel, *, item: Item | None, touched: set[str]) -> None:
        properties = await self._properties(data, item)
        check_properties = item is None or bool(touched & _PROPERTY_DEPENDENT_FIELDS)
        check_weapon(details, properties, check_properties=check_properties)

    async def _after_write(self, item: Item, data: BaseModel) -> None:
        if "property_ids" in data.model_fields_set:
            await self.repository.set_properties(item, getattr(data, "property_ids", None) or [])
