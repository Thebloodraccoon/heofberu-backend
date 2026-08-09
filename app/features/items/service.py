"""Item CRUD service with created_by attribution."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.base_service import BaseService, Page
from app.core.cache import use_cache
from app.features.items.repository import ItemRepository
from app.features.items.schemas import ItemCreate, ItemGetAllResponse, ItemResponse, ItemUpdate
from app.models.item_model import Item


class ItemService(BaseService[Item, ItemCreate, ItemUpdate, ItemResponse, ItemGetAllResponse]):
    """
    Item-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - a delete guard that blocks removing an item still owned by any
        character, since the FK on ``character_items.item_id`` is
        ``ON DELETE RESTRICT`` (unlike Background, whose FK is
        ``SET NULL`` — see ``BackgroundService`` for the contrasting case).

    ``get_by_id``, ``get_all``, and ``delete`` are all inherited
    unchanged from ``BaseService`` — the in-use delete guard is enforced
    by ``BaseRepository.delete`` via ``check_in_use_on_delete=True`` +
    ``ItemRepository.is_in_use``. Listing and detail reads are cached via
    ``@use_cache``.
    """

    repository: ItemRepository

    cache_namespaces = ("items",)

    def __init__(self, db: Session):
        super().__init__(
            repository=ItemRepository(db),
            response_schema=ItemResponse,
            get_all_schema=ItemGetAllResponse,
        )

    @use_cache()
    def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[ItemGetAllResponse]:
        """Cached lightweight listing — see ``BaseService.get_all``."""

        return super().get_all(page=page, size=size, filters=filters, search=search)

    @use_cache()
    def get_by_id(self, item_id: int) -> ItemResponse:
        """Cached single-record fetch — see ``BaseService.get_by_id``."""

        return super().get_by_id(item_id)

    def create_item(self, item_data: ItemCreate, created_by_id: int | None = None) -> ItemResponse:
        """
        Create an item after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant
        mainly for homebrew items) and is not part of ``ItemCreate``
        itself, since it comes from the authenticated user, not client
        input.
        """

        payload = item_data.model_dump()
        payload["created_by_id"] = created_by_id

        item = self.repository.create(payload)
        self._invalidate_cache()
        return self.response_schema.model_validate(item)
