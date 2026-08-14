"""Item CRUD service with created_by attribution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.features.items.cache import ITEM_CACHE_NAMESPACES, invalidate_item_cache
from app.features.items.crud.repository import ItemRepository
from app.features.items.crud.schemas import ItemCreate, ItemGetAllResponse, ItemResponse, ItemUpdate
from app.models.item_model import Item


class ItemCrudService(CachedService[Item, ItemCreate, ItemUpdate, ItemResponse, ItemGetAllResponse]):
    """
    Item-specific CRUD service built on :class:`CachedService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - a delete guard that blocks removing an item still owned by any
        character, since the FK on ``character_items.item_id`` is
        ``ON DELETE RESTRICT`` (unlike Background, whose FK is
        ``SET NULL`` — see ``BackgroundCrudService`` for the contrasting case).

    ``get_by_id``, ``get_all``, and ``delete`` are all inherited
    unchanged from ``CachedService`` — the in-use delete guard is enforced
    by ``BaseRepository.delete`` via ``check_in_use_on_delete=True`` +
    ``ItemRepository.is_in_use``. Listing and detail reads are cached via
    ``@use_cache``.
    """

    repository: ItemRepository

    cache_namespaces = ITEM_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=ItemRepository(db),
            response_schema=ItemResponse,
            get_all_schema=ItemGetAllResponse,
        )

    async def create_item(self, item_data: ItemCreate, created_by_id: int | None = None) -> ItemResponse:
        """
        Create an item after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant
        mainly for homebrew items) and is not part of ``ItemCreate``
        itself, since it comes from the authenticated user, not client
        input.
        """

        payload = item_data.model_dump()
        payload["created_by_id"] = created_by_id

        item = await self.repository.create(payload)
        await invalidate_item_cache()
        return self.response_schema.model_validate(item)
