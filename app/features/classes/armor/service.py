"""Class armor-proficiencies service: full replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES, invalidate_class_cache
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.schemas import ArmorProficienciesUpdate, ClassCreate, ClassResponse, ClassUpdate
from app.models.class_model import Class


class ClassArmorService(BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, None]):
    """
    Everything about a class's armor proficiencies.

    ``set_armor_proficiencies`` is the public full-replace write; the
    ``commit=False`` variant seeds them in the same transaction as the
    class row. Writes purge ``CLASS_CACHE_NAMESPACES``.
    """

    repository: ClassRepository

    cache_namespaces = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with a repository over the session."""

        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
        )

    async def set_armor_proficiencies(self, class_id: int, data: ArmorProficienciesUpdate) -> ClassResponse:
        """Fully replace a class's armor proficiencies."""

        character_class = await self._get_or_404(class_id)

        await self.repository.set_armor_proficiencies(character_class, data.armor_proficiencies)
        await invalidate_class_cache()

        return await self._get_response(class_id)

    async def set_armor_proficiencies_for_class(
        self, character_class: Class, armor_types: list[str], *, commit: bool = True
    ) -> Class:
        """Replace a class's armor proficiencies on an existing row (used by create/update)."""

        return await self.repository.set_armor_proficiencies(character_class, armor_types, commit=commit)
