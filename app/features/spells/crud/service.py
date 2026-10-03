"""Spell CRUD service with transactional class/subclass/race/subrace availability setup."""

from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.service import BeforeUpdateHook
from app.core.base.transaction import invalidate_after_commit
from app.core.cache import use_cache
from app.core.exceptions import RecordNotFoundError
from app.core.pagination import CursorPage, Page, cursor_page, decode_cursor, keyset_condition, paginate
from app.features.spells.cache import SPELL_CACHE_NAMESPACES, spell_cache_namespaces
from app.features.spells.crud.repository import AVAILABILITY_DIMENSIONS, SpellRepository
from app.features.spells.crud.schemas import (
    SpellCreate,
    SpellGetAllResponse,
    SpellResponse,
    SpellUpdate,
)
from app.models import Spell


class SpellCrudService(CachedService[Spell, SpellCreate, SpellUpdate, SpellResponse, SpellGetAllResponse]):
    """
    Spell-specific CRUD service. Creation seeds the availability sets in the
    same transaction; replacing them later lives in the ``availability/``
    subpackage. A rename also purges every cached payload that renders the
    spell's name (see ``spells.cache``).
    """

    repository: SpellRepository

    _LIST_COLUMNS = (Spell.id, Spell.name, Spell.school, Spell.level)

    cache_namespaces = SPELL_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Wire up the spell repository and response schemas."""

        super().__init__(
            repository=SpellRepository(db),
            response_schema=SpellResponse,
            get_all_schema=SpellGetAllResponse,
        )

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict | None = None,
        search: str | None = None,
    ) -> Page[SpellGetAllResponse]:
        """Cached lightweight listing that avoids materializing full Spell rows."""

        skip, limit = paginate(page, size)
        total = await self.repository.count(filters=filters, search=search)
        rows = await self.repository.get_brief(
            *self._LIST_COLUMNS, order_by=Spell.name, skip=skip, limit=limit, filters=filters, search=search
        )
        return Page(items=await self._brief_items(rows), total=total, page=page, size=size)

    async def get_cursor_page(
        self,
        *,
        size: int,
        cursor: str | None,
        filters: dict | None = None,
        search: str | None = None,
    ) -> CursorPage[SpellGetAllResponse]:
        """Keyset listing ordered by ``(name, id)`` (uncached; same filters as :meth:`get_all`)."""

        conditions = []
        if cursor is not None:
            conditions.append(keyset_condition(Spell.name, Spell.id, decode_cursor(cursor, "name")))

        rows = await self.repository.get_brief(
            *self._LIST_COLUMNS,
            order_by=Spell.name,
            limit=size + 1,
            filters=filters,
            search=search,
            conditions=conditions,
        )
        rows, next_cursor = cursor_page(rows, size, "name", lambda row: (row.name, row.id))
        return CursorPage(items=await self._brief_items(rows), next_cursor=next_cursor, size=size)

    async def _brief_items(self, rows: list) -> list[SpellGetAllResponse]:
        """Listing rows merged with their availability sets."""

        availability = await self.repository.load_availability([row[0] for row in rows])
        return [SpellGetAllResponse.model_validate({**row._mapping, **availability.get(row[0], {})}) for row in rows]

    async def create_spell(self, spell_data: SpellCreate) -> SpellResponse:
        """Create a spell after checking its name isn't already taken, seeding any availability set."""

        members_by_dimension = {}
        for dimension in AVAILABILITY_DIMENSIONS:
            ids = getattr(spell_data, dimension.field)
            if ids:
                members_by_dimension[dimension] = await self.resolve_ids(
                    partial(self.repository.get_dimension_members, dimension),
                    ids,
                    dimension.label,
                )

        payload = spell_data.model_dump(exclude={dimension.field for dimension in AVAILABILITY_DIMENSIONS})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)
            for dimension, members in members_by_dimension.items():
                await self.repository.set_availability(item.id, dimension, [m.id for m in members], commit=False)
            await self._invalidate_cache()

        return await self._get_response(item.id)

    async def update(
        self, item_id: int, update_data: SpellUpdate, *, before_update: BeforeUpdateHook | None = None
    ) -> SpellResponse:
        """Partially update a spell; a changed name also purges the catalogs that render it."""

        item = await self._get_or_404(item_id)
        fields = update_data.model_dump(exclude_unset=True)
        if before_update:
            before_update(item, fields)
        renamed = "name" in fields and fields["name"] != item.name

        async with self._atomic():
            await self.repository.update(item, fields, commit=False)
            await self._purge_after_commit(renamed)

        return self.response_schema.model_validate(item)

    async def delete(self, item_id: int) -> bool:
        """Delete a spell, blocked (409) while a character knows/was granted it or a feature effect grants it."""

        item = await self.repository.get_plain(item_id)
        if item is None:
            raise RecordNotFoundError(model_name="Spell", model_id=str(item_id))

        result = await self.repository.delete(item)
        await self._invalidate_cache()

        return result

    async def _purge_after_commit(self, name_changed: bool) -> None:
        """Schedule the cache purge, widened to name-rendering namespaces when the spell was renamed."""

        await invalidate_after_commit(self.repository.db, *spell_cache_namespaces(name_changed=name_changed))
