"""Item CRUD service."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.transaction import invalidate_after_commit
from app.features.items.cache import ITEM_CACHE_NAMESPACES, ITEM_OWN_CACHE_NAMESPACES
from app.features.items.crud.repository import ItemRepository
from app.features.items.crud.schemas import ItemCreate, ItemGetAllResponse, ItemResponse, ItemUpdate
from app.models.items.item_model import Item


class ItemCrudService(CachedService[Item, ItemCreate, ItemUpdate, ItemResponse, ItemGetAllResponse]):
    """
    Item CRUD with a name-uniqueness check and an in-use delete guard.

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

    async def create(self, create_data: ItemCreate) -> ItemResponse:
        """Create an item; nothing references it yet, so only the item listings are purged."""

        item = await self.repository.create(create_data.model_dump())
        await invalidate_after_commit(self.repository.db, *ITEM_OWN_CACHE_NAMESPACES)

        return self.response_schema.model_validate(item)

    async def delete(self, item_id: int) -> bool:
        """Delete an unused item; only the item listings can hold it."""

        item = await self._get_or_404(item_id)
        result = await self.repository.delete(item)
        await invalidate_after_commit(self.repository.db, *ITEM_OWN_CACHE_NAMESPACES)

        return result
