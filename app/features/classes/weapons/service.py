"""Class weapon-proficiencies service: full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES, invalidate_class_cache
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.schemas import ClassCreate, ClassResponse, ClassUpdate, WeaponProficienciesUpdate
from app.models.class_model import Class


class ClassWeaponService(BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, None]):
    """
    Everything about a class's weapon proficiencies.

    ``set_weapon_proficiencies`` is the public full-replace write; the
    ``commit=False`` variant is shared with ``create_class``/``update_class``
    so weapon proficiencies seed in the same transaction as the class row.
    Any write purges every namespace listed in :data:`CLASS_CACHE_NAMESPACES`.
    """

    repository: ClassRepository

    cache_namespaces = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
        )

    async def set_weapon_proficiencies(self, class_id: int, data: WeaponProficienciesUpdate) -> ClassResponse:
        character_class = await self._get_or_404(class_id)

        await self.repository.set_weapon_proficiencies(character_class, data.weapon_proficiencies)
        await invalidate_class_cache()

        return await self._get_response(class_id)

    async def set_weapon_proficiencies_for_class(
        self, character_class: Class, weapon_categories: list[str], *, commit: bool = True
    ) -> Class:
        """Replace a class's weapon proficiencies on an existing row (used by create/update)."""

        return await self.repository.set_weapon_proficiencies(character_class, weapon_categories, commit=commit)
