"""Spell availability service: full replacement of a spell's class/subclass/race/subrace availability."""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.spells.availability.schemas import (
    ClassAvailabilityUpdate,
    RaceAvailabilityUpdate,
    SubclassAvailabilityUpdate,
    SubraceAvailabilityUpdate,
)
from app.features.spells.cache import SPELL_CACHE_NAMESPACES
from app.features.spells.crud.repository import AvailabilityDimension, SpellRepository, availability_dimension
from app.features.spells.crud.schemas import SpellResponse
from app.models import Spell


class SpellAvailabilityService(BaseService[Spell, BaseModel, BaseModel, SpellResponse]):
    """Full-replace writes for a spell's class/subclass/race/subrace availability."""

    repository: SpellRepository

    cache_namespaces = SPELL_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialise with a spell repository and response schema."""

        super().__init__(
            repository=SpellRepository(db),
            response_schema=SpellResponse,
        )

    async def _replace(self, dimension: AvailabilityDimension, spell_id: int, ids: list[int]) -> SpellResponse:
        """Replace one dimension of an existing spell in one transaction. Empty list = unrestricted."""

        await self._exists_or_404(spell_id)
        members = await self.resolve_ids(
            lambda wanted: self.repository.get_dimension_members(dimension, wanted), ids, dimension.label
        )

        async with self._atomic():
            await self.repository.set_availability(spell_id, dimension, [member.id for member in members])
            await self._invalidate_cache()

        return await self._get_response(spell_id)

    async def set_classes(self, spell_id: int, data: ClassAvailabilityUpdate) -> SpellResponse:
        """Fully replace the classes a spell is available to."""

        return await self._replace(availability_dimension("available_classes"), spell_id, data.class_ids)

    async def set_subclasses(self, spell_id: int, data: SubclassAvailabilityUpdate) -> SpellResponse:
        """Fully replace the subclasses a spell is available to."""

        return await self._replace(availability_dimension("available_subclasses"), spell_id, data.subclass_ids)

    async def set_races(self, spell_id: int, data: RaceAvailabilityUpdate) -> SpellResponse:
        """Fully replace the races a spell is available to."""

        return await self._replace(availability_dimension("available_races"), spell_id, data.race_ids)

    async def set_subraces(self, spell_id: int, data: SubraceAvailabilityUpdate) -> SpellResponse:
        """Fully replace the subraces a spell is available to."""

        return await self._replace(availability_dimension("available_subraces"), spell_id, data.subrace_ids)
