"""Per-capability dependency providers for the items domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.items.armor.service import ArmorService
from app.features.items.crud.service import ItemCrudService
from app.features.items.effects.service import ItemEffectsService
from app.features.items.properties.service import WeaponPropertyService
from app.features.items.tools.service import ToolService
from app.features.items.weapons.service import WeaponService


def get_item_crud_service(db: DatabaseDep) -> ItemCrudService:
    """Build the item core service instance."""

    return ItemCrudService(db)


def get_weapon_service(db: DatabaseDep) -> WeaponService:
    """Build the weapon service."""

    return WeaponService(db)


def get_armor_service(db: DatabaseDep) -> ArmorService:
    """Build the armor service."""

    return ArmorService(db)


def get_tool_service(db: DatabaseDep) -> ToolService:
    """Build the tool service."""

    return ToolService(db)


def get_weapon_property_service(db: DatabaseDep) -> WeaponPropertyService:
    """Build the weapon-property dictionary service."""

    return WeaponPropertyService(db)


def get_item_effects_service(db: DatabaseDep) -> ItemEffectsService:
    """Build the item-effects service."""

    return ItemEffectsService(db)


ItemCrudDep = Annotated[ItemCrudService, Depends(get_item_crud_service)]
WeaponServiceDep = Annotated[WeaponService, Depends(get_weapon_service)]
ArmorServiceDep = Annotated[ArmorService, Depends(get_armor_service)]
ToolServiceDep = Annotated[ToolService, Depends(get_tool_service)]
WeaponPropertyDep = Annotated[WeaponPropertyService, Depends(get_weapon_property_service)]
ItemEffectsDep = Annotated[ItemEffectsService, Depends(get_item_effects_service)]
