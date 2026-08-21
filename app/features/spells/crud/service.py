"""Spell CRUD service with transactional class/race availability setup."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.features.spells.availability.service import SpellAvailabilityService
from app.features.spells.cache import SPELL_CACHE_NAMESPACES, invalidate_spell_cache
from app.features.spells.crud.repository import SpellRepository
from app.features.spells.crud.schemas import (
    SpellCreate,
    SpellGetAllResponse,
    SpellResponse,
    SpellUpdate,
)
from app.models import Spell


class SpellCrudService(CachedService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellGetAllResponse]):
    """
    Spell-specific CRUD service built on :class:`CachedService`.

    Adds behaviors the generic base class doesn't provide:
      - the inherited paginated ``get_all`` (ordered by ``Spell.id``,
        searchable on ``name``), served as a lightweight ``Page`` cached
        transparently in Redis via ``@use_cache``;
      - a uniqueness check on ``name`` before create/update;
      - ``create_spell``, which can optionally set class/race availability
        up front, in the same transaction as the spell itself. An empty
        (or omitted) list on either side means the spell is
        unrestricted for that dimension.

    Class/race availability management (the ``PUT /spells/{spell_id}/classes``
    /``races`` endpoints) lives in the dedicated ``availability/``
    subpackage; ``create_spell`` delegates its seeding there via
    :class:`SpellAvailabilityService`.
    """

    repository: SpellRepository

    cache_namespaces = SPELL_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SpellRepository(db),
            response_schema=SpellResponse,
            get_all_schema=SpellGetAllResponse,
        )
        self._availability = SpellAvailabilityService(db)

    async def create_spell(self, spell_data: SpellCreate) -> SpellResponse:
        """
        Create a spell after checking its name isn't already taken.

        ``spell_data.available_classes`` / ``available_races`` are
        optional. If supplied, they're set in the *same transaction* as
        the spell itself, mirroring ``RaceService.create_race``. Every
        write inside the nested transaction below passes ``commit=False``
        for the same reason documented there: a plain ``session.commit()``
        from any of them would commit the entire outer transaction, not
        just the ``begin_nested()`` SAVEPOINT.
        """

        classes = (
            await self.resolve_ids(self.repository.get_classes_by_ids, spell_data.available_classes, "Classes")
            if spell_data.available_classes
            else None
        )
        races = (
            await self.resolve_ids(self.repository.get_races_by_ids, spell_data.available_races, "Races")
            if spell_data.available_races
            else None
        )

        payload = spell_data.model_dump(exclude={"available_classes", "available_races"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if classes:
                await self._availability.set_classes_for_spell(item, classes, commit=False)

            if races:
                await self._availability.set_races_for_spell(item, races, commit=False)

        await invalidate_spell_cache()

        return await self._get_response(item.id)
