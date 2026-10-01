"""Tag CRUD service with in-use delete guard."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.service import Page
from app.core.base.transaction import invalidate_after_commit
from app.core.exceptions import RecordNotFoundError
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

    async def create(self, create_data: TagCreate) -> TagResponse:
        """
        A new tag starts unattached to any record, so it can't be embedded in any
        cached payload yet (not even its own, new-id ``get_by_id``) — skip the flush.
        """

        item = await self.repository.create(create_data.model_dump())
        return self.response_schema.model_validate(item)

    async def delete(self, item_id: int) -> bool:
        """
        Delete an unattached tag (409 while anything still carries it).

        Only the tag dictionary's own cache is purged: an unattached tag is embedded in no
        race/background/article payload, so those namespaces stay warm (a rename, by contrast, purges them).
        """

        item = await self._get_or_404(item_id)
        result = await self.repository.delete(item)
        await invalidate_after_commit(self.repository.db, "tags")
        return result

    async def get_tag(self, tag_id: int, *, include_hidden: bool) -> TagResponse:
        """Cached read; 404 for a non-GM if no record they can see carries the tag (its name may be a spoiler)."""

        tag = await self.get_by_id(tag_id)
        if not include_hidden and not await self.repository.is_visible(tag_id):
            raise RecordNotFoundError(model_name="Tag", model_id=str(tag_id))

        return tag

    async def list_tags(
        self, *, page: int, size: int, search: str | None, sort: str, include_hidden: bool
    ) -> Page[TagGetAllResponse]:
        """Paginated tags with usage counts (not cached: the counts change whenever any catalog re-tags a record)."""

        rows, total = await self.repository.list_with_usage(
            page=page, size=size, search=search, sort=sort, include_hidden=include_hidden
        )
        items = [TagGetAllResponse.model_validate(row) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def suggest(self, query: str, limit: int, *, include_hidden: bool) -> list[TagGetAllResponse]:
        """Autocomplete suggestions for a tag picker."""

        rows = await self.repository.suggest(query, limit, include_hidden=include_hidden)
        return [TagGetAllResponse.model_validate(row) for row in rows]
