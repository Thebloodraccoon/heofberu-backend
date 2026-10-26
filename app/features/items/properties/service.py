"""Weapon-property service: the dictionary's CRUD; a write purges the cached item payloads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.items.cache import ITEM_OWN_CACHE_NAMESPACES
from app.features.items.properties.repository import WeaponPropertyRepository
from app.features.items.properties.schemas import (
    WeaponPropertyCreate,
    WeaponPropertyResponse,
    WeaponPropertyUpdate,
)
from app.models.items.weapon_property_model import WeaponProperty


class WeaponPropertyService(
    BaseService[WeaponProperty, WeaponPropertyCreate, WeaponPropertyUpdate, WeaponPropertyResponse]
):
    """Create/update/delete purge only ``items`` (items embed their properties; no dependent does)."""

    repository: WeaponPropertyRepository
    cache_namespaces = ITEM_OWN_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Wire up the repository and the response schema."""

        super().__init__(repository=WeaponPropertyRepository(db), response_schema=WeaponPropertyResponse)

    async def list_properties(self) -> list[WeaponPropertyResponse]:
        """Every weapon property, by name."""

        return [WeaponPropertyResponse.model_validate(row) for row in await self.repository.list_all()]
