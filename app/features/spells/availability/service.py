"""Spell availability service: full replacement of a spell's class/race availability."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.spells.availability.schemas import ClassAvailabilityUpdate, RaceAvailabilityUpdate
from app.features.spells.cache import invalidate_spell_cache
from app.features.spells.crud.repository import SpellRepository
from app.features.spells.crud.schemas import SpellCreate, SpellResponse, SpellUpdate
from app.models.class_model import Class
from app.models.race_model import Race
from app.models.spell_model import Spell


class SpellAvailabilityService(BaseService[Spell, SpellCreate, SpellUpdate, SpellResponse, None]):
    """
    Everything about a spell's class/race availability.

    ``set_classes`` / ``set_races`` are the public full-replace writes;
    the ``commit=False`` variants (``set_classes_for_spell`` /
    ``set_races_for_spell``) are shared with ``create_spell`` so a spell's
    availability seeds in the same transaction as the spell row. Any write
    purges the ``spells`` namespace via :func:`invalidate_spell_cache`.
    """

    repository: SpellRepository

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SpellRepository(db),
            response_schema=SpellResponse,
        )

    async def set_classes(self, spell_id: int, data: ClassAvailabilityUpdate) -> SpellResponse:
        """Fully replace the classes a spell is available to. Empty list = unrestricted."""

        spell = await self._get_or_404(spell_id)
        classes = await self.resolve_ids(self.repository.get_classes_by_ids, data.class_ids, "Classes")

        await self.repository.set_classes(spell, classes)
        await invalidate_spell_cache()

        return await self._get_response(spell_id)

    async def set_races(self, spell_id: int, data: RaceAvailabilityUpdate) -> SpellResponse:
        """Fully replace the races a spell is available to. Empty list = unrestricted."""

        spell = await self._get_or_404(spell_id)
        races = await self.resolve_ids(self.repository.get_races_by_ids, data.race_ids, "Races")

        await self.repository.set_races(spell, races)
        await invalidate_spell_cache()

        return await self._get_response(spell_id)

    async def set_classes_for_spell(self, spell: Spell, classes: list[Class], *, commit: bool = True) -> None:
        """Replace a spell's classes on an existing ``spell`` row (used by ``create_spell``)."""

        await self.repository.set_classes(spell, classes, commit=commit)

    async def set_races_for_spell(self, spell: Spell, races: list[Race], *, commit: bool = True) -> None:
        """Replace a spell's races on an existing ``spell`` row (used by ``create_spell``)."""

        await self.repository.set_races(spell, races, commit=commit)
