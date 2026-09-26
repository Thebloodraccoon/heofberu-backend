"""Tag CRUD service with in-use delete guard."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.service import Page
from app.features.tags.cache import TAG_CACHE_NAMESPACES
from app.features.tags.crud.repository import TagRepository
from app.features.tags.crud.schemas import TagCreate, TagGetAllResponse, TagResponse, TagUpdate
from app.models.tag_model import Tag


class TagCrudService(CachedService[Tag, TagCreate, TagUpdate, TagResponse, TagGetAllResponse]):
    """
    Tag dictionary CRUD.

    This is the ONLY place a new tag is created — races/subraces/backgrounds/
    articles only ever attach EXISTING tag ids (``PUT .../{id}/tags`` in each
    catalog's own ``tags/`` capability, via ``TagsManagerMixin``); they never
    create one implicitly by name.
    """

    repository: TagRepository

    cache_namespaces = TAG_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Wire up the tag repository, response schema, and get-all schema."""

        super().__init__(
            repository=TagRepository(db),
            response_schema=TagResponse,
            get_all_schema=TagGetAllResponse,
        )

    async def list_tags(self, *, page: int, size: int, search: str | None, sort: str) -> Page[TagGetAllResponse]:
        """Paginated tags with usage counts (not cached: the counts change whenever any catalog re-tags a record)."""

        rows, total = await self.repository.list_with_usage(page=page, size=size, search=search, sort=sort)
        items = [TagGetAllResponse.model_validate(row) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def suggest(self, query: str, limit: int) -> list[TagGetAllResponse]:
        """Autocomplete suggestions for a tag picker."""

        rows = await self.repository.suggest(query, limit)
        return [TagGetAllResponse.model_validate(row) for row in rows]
