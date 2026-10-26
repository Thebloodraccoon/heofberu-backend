"""Weapon-property repository: base CRUD with a name-uniqueness check and an in-use guard."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.items.weapon_property_model import WeaponProperty, item_weapon_properties


class WeaponPropertyRepository(BaseRepository[WeaponProperty]):
    """A property can't be deleted while a weapon still has it."""

    def __init__(self, db: AsyncSession):
        """Configure name uniqueness and the delete guard."""

        super().__init__(WeaponProperty, db, unique_fields=["name"], check_in_use_on_delete=True)

    async def list_all(self) -> list[WeaponProperty]:
        """Every property, by name (the dictionary is small: no paging)."""

        return list((await self.db.execute(select(WeaponProperty).order_by(WeaponProperty.name))).scalars().all())

    async def is_in_use(self, model_id: int) -> bool:
        """Whether any weapon has the property."""

        statement = select(item_weapon_properties.c.item_id).where(item_weapon_properties.c.property_id == model_id)
        return await self.db.scalar(statement.limit(1)) is not None
