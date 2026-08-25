"""Spell CRUD service with transactional class/subclass/race/subrace availability setup."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.service import Page, paginate
from app.core.cache import use_cache
from app.features.spells.availability.service import SpellAvailabilityService
from app.features.spells.cache import SPELL_CACHE_NAMESPACES, invalidate_spell_cache
from app.features.spells.crud.repository import SpellRepository
from app.features.spells.crud.schemas import (
    SpellCreate,
    SpellGetAllResponse,
    SpellResponse,
    SpellUpdate,
)
from app.models import Class, Race, Spell, Subclass, Subrace
from app.models.spell_association_models import spell_classes, spell_races, spell_subclasses, spell_subraces

_EMPTY_AVAILABILITY = {
    "available_classes": [],
    "available_subclasses": [],
    "available_races": [],
    "available_subraces": [],
}


class SpellCrudService(CachedService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellGetAllResponse]):
    """
    Spell-specific CRUD service built on :class:`CachedService`.

    Adds behaviors the generic base class doesn't provide:
      - the inherited paginated ``get_all`` (ordered by ``Spell.id``,
        searchable on ``name``), served as a lightweight ``Page`` cached
        transparently in Redis via ``@use_cache``;
      - a uniqueness check on ``name`` before create/update;
      - ``create_spell``, which can optionally set class/subclass/race/
        subrace availability up front, in the same transaction as the
        spell itself. An empty (or omitted) list on any side means the
        spell is unrestricted for that dimension.

    Class/subclass/race/subrace availability management (the
    ``PUT /spells/{spell_id}/classes`` / ``subclasses`` / ``races`` /
    ``subraces`` endpoints) lives in the dedicated ``availability/``
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

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict | None = None,
        search: str | None = None,
    ) -> Page[SpellGetAllResponse]:
        """
        Cached listing, built WITHOUT materializing full ``Spell`` rows.

        The generic base path would fall back to the eager-loaded
        ``repository.get_all`` because the listing schema embeds the four
        availability relationships — pulling every spell's full ``description``
        Text and component columns only to drop them at serialization. This
        override instead column-selects the scalar fields and loads each
        availability dimension with one join query per page.
        """

        skip, limit = paginate(page, size)
        total = await self.repository.count(filters=filters, search=search)

        rows = await self.repository.get_brief(
            Spell.id,
            Spell.name,
            Spell.school,
            Spell.level,
            order_by=Spell.id,
            skip=skip,
            limit=limit,
            filters=filters,
            search=search,
        )
        page_ids = [row[0] for row in rows]

        availability = await self._load_availability(page_ids) if page_ids else {}

        items = [
            SpellGetAllResponse.model_validate(
                {
                    **row._mapping,
                    **availability.get(row[0], _EMPTY_AVAILABILITY),
                }
            )
            for row in rows
        ]
        return Page(items=items, total=total, page=page, size=size)

    async def _load_availability(self, spell_ids: list[int]) -> dict[int, dict]:
        """One join query per availability dimension; returns ``{spell_id: {field: [{id, name}]}}``."""

        dimensions = (
            ("available_classes", spell_classes, "class_id", Class),
            ("available_subclasses", spell_subclasses, "subclass_id", Subclass),
            ("available_races", spell_races, "race_id", Race),
            ("available_subraces", spell_subraces, "subrace_id", Subrace),
        )

        result: dict[int, dict] = {spell_id: {} for spell_id in spell_ids}
        for field, table, child_fk, child_model in dimensions:
            stmt = (
                select(table.c.spell_id, child_model.id, child_model.name)
                .join(child_model, child_model.id == getattr(table.c, child_fk))
                .where(table.c.spell_id.in_(spell_ids))
                .order_by(table.c.spell_id, child_model.id)
            )
            rows = (await self.repository.db.execute(stmt)).all()
            for spell_id, child_id, child_name in rows:
                result.setdefault(spell_id, {}).setdefault(field, []).append({"id": child_id, "name": child_name})

        return result

    async def create_spell(self, spell_data: SpellCreate) -> SpellResponse:
        """
        Create a spell after checking its name isn't already taken.

        ``spell_data.available_classes`` / ``available_subclasses`` /
        ``available_races`` / ``available_subraces`` are optional. If
        supplied, they're set in the *same transaction* as the spell
        itself, mirroring ``RaceService.create_race``. Every write inside
        the nested transaction below passes ``commit=False`` for the same
        reason documented there: a plain ``session.commit()`` from any of
        them would commit the entire outer transaction, not just the
        ``begin_nested()`` SAVEPOINT.
        """

        classes = (
            await self.resolve_ids(self.repository.get_classes_by_ids, spell_data.available_classes, "Classes")
            if spell_data.available_classes
            else None
        )
        subclasses = (
            await self.resolve_ids(self.repository.get_subclasses_by_ids, spell_data.available_subclasses, "Subclasses")
            if spell_data.available_subclasses
            else None
        )
        races = (
            await self.resolve_ids(self.repository.get_races_by_ids, spell_data.available_races, "Races")
            if spell_data.available_races
            else None
        )
        subraces = (
            await self.resolve_ids(self.repository.get_subraces_by_ids, spell_data.available_subraces, "Subraces")
            if spell_data.available_subraces
            else None
        )

        payload = spell_data.model_dump(
            exclude={
                "available_classes",
                "available_subclasses",
                "available_races",
                "available_subraces",
            }
        )

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if classes:
                await self._availability.set_classes_for_spell(item, classes, commit=False)

            if subclasses:
                await self._availability.set_subclasses_for_spell(item, subclasses, commit=False)

            if races:
                await self._availability.set_races_for_spell(item, races, commit=False)

            if subraces:
                await self._availability.set_subraces_for_spell(item, subraces, commit=False)

        await invalidate_spell_cache()
        return await self._get_response(item.id)
