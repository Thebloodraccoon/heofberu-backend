"""Item CRUD service."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.features.items.cache import ITEM_CACHE_NAMESPACES, invalidate_item_cache
from app.features.items.crud.repository import ItemRepository
from app.features.items.crud.schemas import ItemCreate, ItemGetAllResponse, ItemResponse, ItemUpdate
from app.models.item_model import Item


class ItemCrudService(CachedService[Item, ItemCreate, ItemUpdate, ItemResponse, ItemGetAllResponse]):
    """Item-specific CRUD service. Adds a name-uniqueness check and an in-use delete guard."""

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

    async def create_item(self, item_data: ItemCreate) -> ItemResponse:
        """Create an item after checking its name isn't already taken."""

        item = await self.repository.create(item_data.model_dump())
        await invalidate_item_cache()
        return self.response_schema.model_validate(item)
