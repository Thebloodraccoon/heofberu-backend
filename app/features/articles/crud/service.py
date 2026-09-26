"""Article CRUD service: cached catalog CRUD plus composed capability reads."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ArticleStatus, is_article_publicly_visible
from app.core.base.cached_service import CachedService
from app.core.base.service import Page
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.articles.cache import ARTICLE_CACHE_NAMESPACES, invalidate_article_cache
from app.features.articles.crud.repository import ArticleRepository
from app.features.articles.crud.schemas import (
    ArticleBrief,
    ArticleCreate,
    ArticleGetAllResponse,
    ArticleResponse,
    ArticleSearchResult,
    ArticleUpdate,
)
from app.features.articles.exceptions import ArticleParentCycleException
from app.features.articles.images.service import storage_entity
from app.features.articles.secrets import strip_gm_blocks
from app.models.articles.article_model import Article


class ArticleCrudService(
    CachedService[Article, ArticleCreate, ArticleUpdate, ArticleResponse, ArticleGetAllResponse],
):
    """Article catalog CRUD."""

    repository: ArticleRepository

    cache_namespaces = ARTICLE_CACHE_NAMESPACES
    get_all_order_by = "title"

    def __init__(self, db: AsyncSession, storage: ImageStorageService | None = None):
        """Initialize the article repository and the storage backend used to clean up gallery images on delete."""

        super().__init__(
            repository=ArticleRepository(db),
            response_schema=ArticleResponse,
            get_all_schema=ArticleGetAllResponse,
        )
        self._storage = storage or ImageStorageService()

    async def create_article(self, data: ArticleCreate, author_id: int | None = None) -> ArticleResponse:
        """
        Create an article (identity/content fields only), generate its slug from the title,
        stamp its author, and seed its ``path``.

        ``tags``/``images`` are not seeded here — attached afterwards through
        their own capability endpoints, mirroring ``RaceCrudService.create_race``.
        """

        await self._validate_parent(data.parent_id)

        async with self._atomic():
            slug = await self.repository.generate_unique_slug(data.title)
            item = await self.repository.create({**data.model_dump(), "slug": slug, "author_id": author_id}, commit=False)
            await self.repository.set_path(item.id, data.parent_id, commit=False)

        await invalidate_article_cache()

        return await self._get_response(item.id)

    async def update_article(self, article_id: int, data: ArticleUpdate) -> ArticleResponse:
        """
        Partially update an article.

        Including ``parent_id`` re-roots ``path`` for the article and every
        existing descendant, and is rejected if it would create a cycle or
        point at a missing article. The first transition to ``PUBLISHED``
        stamps ``published_at``. The field update and the path rewrite share
        one transaction.
        """

        fields = data.model_dump(exclude_unset=True)
        item = await self._get_or_404(article_id)

        if "parent_id" in fields:
            await self._validate_parent(fields["parent_id"], article_id)

        if fields.get("status") == ArticleStatus.PUBLISHED and item.published_at is None:
            fields["published_at"] = datetime.now(timezone.utc)

        async with self._atomic():
            await self.repository.apply_update(item, fields, commit=False)
            if "parent_id" in fields:
                await self.repository.set_path(article_id, fields["parent_id"], commit=False)

        await invalidate_article_cache()

        return await self._get_response(article_id)

    async def delete(self, item_id: int) -> bool:
        """
        Delete an article, then best-effort remove its gallery images from storage.

        The row delete and every child's path fix-up share one ``_atomic()``
        transaction, so a failure partway through leaves nothing half-applied.
        Cache invalidation runs once, after that transaction commits.

        Storage cleanup for gallery images runs last and outside the
        transaction — Storage knows nothing about Postgres rollback, so the
        DB write must have already succeeded before objects are removed (a
        storage failure is logged inside ``ImageStorageService.delete_image``,
        never raised).

        Direct children are detached, not deleted (``ondelete="SET NULL"``) —
        that FK action only clears their ``parent_id``, so each child's
        (and its whole existing subtree's) ``path`` is re-rooted in the same
        transaction via ``set_path``, otherwise it would keep pointing under
        the deleted article's now-stale path.
        """

        item = await self._get_or_404(item_id)
        image_ids = await self.repository.list_image_ids(item_id)
        child_ids = await self.repository.list_child_ids(item_id)

        async with self._atomic():
            await self.repository.db.delete(item)
            for child_id in child_ids:
                await self.repository.set_path(child_id, None, commit=False)

        await self._invalidate_cache()

        for image_id in image_ids:
            await self._storage.delete_image(storage_entity(item_id), image_id)

        return True

    async def get_article(self, article_id: int, *, include_hidden: bool) -> ArticleResponse:
        """
        Cached detail read, with the visibility check applied AFTER the cache so one
        cached payload serves every reader. Hidden articles 404 (not 403) for non-GMs,
        so their existence isn't revealed.

        ``parent_id`` is likewise nulled out for a non-GM reader when the parent
        itself isn't visible, so a hidden article's id/existence can't leak
        through a public child's detail response, GM-only ``:::gm`` blocks
        are stripped from ``body_markdown``, and ``images`` is emptied.
        """

        article = await self.get_by_id(article_id)
        if include_hidden:
            return article

        if not is_article_publicly_visible(article.status, article.visibility):
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

        # Images reach readers only through ``![alt](url)`` in the (stripped) body; the raw
        # list would also leak ones placed inside :::gm blocks or not embedded at all.
        update: dict = {"body_markdown": strip_gm_blocks(article.body_markdown), "images": []}
        if article.parent_id is not None and not await self.repository.exists_visible(article.parent_id, False):
            update["parent_id"] = None

        return article.model_copy(update=update)

    async def list_articles(
        self,
        *,
        page: int,
        size: int,
        include_hidden: bool,
        search: str | None,
        article_types: list[str] | None,
        subtype: str | None,
        parent_id: int | None,
        tag_ids: list[int] | None,
        match_all_tags: bool,
        sort: str,
    ) -> Page[ArticleGetAllResponse]:
        """Filtered/sorted listing (not cached: results depend on the reader's visibility and the filters)."""

        rows, total = await self.repository.list_articles(
            page=page,
            size=size,
            include_hidden=include_hidden,
            search=search,
            article_types=article_types,
            subtype=subtype,
            parent_id=parent_id,
            tag_ids=tag_ids,
            match_all_tags=match_all_tags,
            sort=sort,
        )
        items = [ArticleGetAllResponse.model_validate(row) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def search_articles(
        self,
        query: str,
        *,
        page: int,
        size: int,
        include_hidden: bool,
        article_types: list[str] | None,
        subtype: str | None,
        tag_ids: list[int] | None,
        match_all_tags: bool,
    ) -> Page[ArticleSearchResult]:
        """Ranked full-text search over visible articles."""

        rows, total = await self.repository.search_articles(
            query,
            page=page,
            size=size,
            include_hidden=include_hidden,
            article_types=article_types,
            subtype=subtype,
            tag_ids=tag_ids,
            match_all_tags=match_all_tags,
        )
        items = [ArticleSearchResult.model_validate(row) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def get_children(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Return the direct children of an article. 404s if the article isn't visible to the reader."""

        await self._exists_visible_or_404(article_id, include_hidden)
        rows = await self.repository.list_children(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    async def get_descendants(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Return every descendant of an article at any depth. 404s if the article isn't visible to the reader."""

        await self._exists_visible_or_404(article_id, include_hidden)
        rows = await self.repository.list_descendants(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    async def get_ancestors(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Return the breadcrumb chain (root-first) above an article. 404s if the article isn't visible."""

        await self._exists_visible_or_404(article_id, include_hidden)
        rows = await self.repository.list_ancestors(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    async def get_latest(
        self, limit: int, article_types: list[str] | None, *, include_hidden: bool
    ) -> list[ArticleGetAllResponse]:
        """Return the most recently published articles, newest first."""

        rows = await self.repository.list_latest(limit, article_types=article_types, include_hidden=include_hidden)
        return [ArticleGetAllResponse.model_validate(row) for row in rows]

    async def _exists_visible_or_404(self, article_id: int, include_hidden: bool) -> None:
        """Raise ``RecordNotFoundError`` unless the article exists and the reader may see it."""

        if not await self.repository.exists_visible(article_id, include_hidden):
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

    async def _validate_parent(self, parent_id: int | None, article_id: int | None = None) -> None:
        """Reject a ``parent_id`` that doesn't exist or (when ``article_id`` is given) would create a cycle."""

        if parent_id is None:
            return

        if not await self.repository.exists_by_id(parent_id):
            raise RecordIdsInvalidError(model_name="Article", ids=[parent_id])

        if article_id is not None and await self.repository.is_self_or_descendant(article_id, parent_id):
            raise ArticleParentCycleException(article_id=article_id, parent_id=parent_id)
