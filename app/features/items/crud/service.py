"""Item core service: listing/detail reads, ``GEAR`` creation, core PATCH and delete."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ItemKind
from app.core.base.cached_service import CachedService
from app.core.base.transaction import invalidate_after_commit
from app.core.cache import use_cache
from app.core.pagination import Page, paginate
from app.features.items.cache import ITEM_CACHE_NAMESPACES, ITEM_OWN_CACHE_NAMESPACES
from app.features.items.crud.repository import ItemRepository
from app.features.items.crud.schemas import GearCreate, ItemCoreUpdate, ItemGetAllResponse, ItemResponse
from app.features.items.exceptions import InvalidItemDataError
from app.models.items.item_model import Item


class ItemCrudService(CachedService[Item, GearCreate, ItemCoreUpdate, ItemResponse, ItemGetAllResponse]):
    """
    The core of every item: cached reads, ``GEAR`` creation (``POST /items``), core PATCH and the in-use
    delete guard. A weapon/armor/tool is created and its stats edited by its kind's package
    (``items/{weapons,armor,tools}``, see :mod:`app.features.items.crud.kinds`); ``kind`` never changes.

    Updates purge every namespace that embeds item data; create and delete
    only touch the item listings (see :mod:`app.features.items.cache`).
    """

    repository: ItemRepository

    cache_namespaces = ITEM_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Wire up the item repository, response schema, and get-all schema."""

        super().__init__(
            repository=ItemRepository(db),
            response_schema=ItemResponse,
            get_all_schema=ItemGetAllResponse,
        )

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict | None = None,
        search: str | None = None,
    ) -> Page[ItemGetAllResponse]:
        """
        Cached listing from one column select (``ItemRepository.get_listing``): the categories are detail-record
        columns, not ``Item`` columns, so the base column path would fall back to full rows with every eager load.
        """

        skip, limit = paginate(page, size)
        total = await self.repository.count(filters=filters, search=search)
        rows = await self.repository.get_listing(skip=skip, limit=limit, filters=filters, search=search)
        return Page(
            items=[ItemGetAllResponse.model_validate(row._mapping) for row in rows], total=total, page=page, size=size
        )

    async def create(self, create_data: GearCreate) -> ItemResponse:
        """Create a ``GEAR`` item; nothing references it yet, so only the item listings are purged."""

        async with self._atomic():
            item = await self.repository.create({**create_data.model_dump(), "kind": ItemKind.GEAR})
            await invalidate_after_commit(self.repository.db, *ITEM_OWN_CACHE_NAMESPACES)

        return self.response_schema.model_validate(await self.repository.get_fresh(item.id))

    async def update(self, item_id: int, update_data: ItemCoreUpdate, **_: Any) -> ItemResponse:
        """PATCH the core; ``subtype`` belongs to a ``GEAR`` item only (422 otherwise)."""

        item = await self._get_or_404(item_id)
        changes = update_data.model_dump(exclude_unset=True)
        if "subtype" in changes and item.kind != ItemKind.GEAR:
            raise InvalidItemDataError(f"subtype applies to a GEAR item only; this one is a {item.kind.value}.")

        async with self._atomic():
            await self.repository.update(item, changes)
            await self._invalidate_cache()

        return self.response_schema.model_validate(await self.repository.get_fresh(item_id))

    async def delete(self, item_id: int) -> bool:
        """Delete an unused item (its detail record, properties and effects cascade); only the listings change."""

        item = await self._get_or_404(item_id)
        async with self._atomic():
            result = await self.repository.delete(item)
            await invalidate_after_commit(self.repository.db, *ITEM_OWN_CACHE_NAMESPACES)

        return result
