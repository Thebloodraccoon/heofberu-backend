"""Article tree navigation: children, descendants and the breadcrumb chain, cached per article and reader kind."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import use_cache
from app.core.exceptions import RecordNotFoundError
from app.features.articles.cache import ARTICLE_TREE_NAMESPACE
from app.features.articles.crud.schemas import ArticleBrief
from app.features.articles.tree.repository import ArticleTreeRepository


class ArticleTreeService:
    """
    Read side of the article tree (writes go through ``ArticleWriter`` / ``ArticleCrudService``).

    Each public method first checks, uncached, that the article exists and the reader may see it (404 otherwise),
    then serves the list from ``article_trees`` keyed by ``(article_id, include_hidden)``. The namespace is purged
    by any article write that changes what a brief shows (``cache.TREE_PAYLOAD_FIELDS``), status or existence.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the tree repository."""

        self.repository = ArticleTreeRepository(db)

    async def get_children(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Direct children of the article the reader may see; 404 if the article itself isn't visible."""

        await self._exists_visible_or_404(article_id, include_hidden)
        return await self._cached_children(article_id, include_hidden=include_hidden)

    async def get_descendants(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Visible descendants at any depth (capped, see ``TREE_LIST_LIMIT``); 404 if the article isn't visible."""

        await self._exists_visible_or_404(article_id, include_hidden)
        return await self._cached_descendants(article_id, include_hidden=include_hidden)

    async def get_ancestors(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Visible ancestors, root first (breadcrumbs); 404 if the article isn't visible."""

        await self._exists_visible_or_404(article_id, include_hidden)
        return await self._cached_ancestors(article_id, include_hidden=include_hidden)

    @use_cache(namespace=ARTICLE_TREE_NAMESPACE)
    async def _cached_children(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Cached body of ``get_children`` (no visibility check of ``article_id`` itself)."""

        rows = await self.repository.list_children(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    @use_cache(namespace=ARTICLE_TREE_NAMESPACE)
    async def _cached_descendants(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Cached body of ``get_descendants`` (no visibility check of ``article_id`` itself)."""

        rows = await self.repository.list_descendants(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    @use_cache(namespace=ARTICLE_TREE_NAMESPACE)
    async def _cached_ancestors(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Cached body of ``get_ancestors`` (no visibility check of ``article_id`` itself)."""

        rows = await self.repository.list_ancestors(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    async def _exists_visible_or_404(self, article_id: int, include_hidden: bool) -> None:
        """Raise ``RecordNotFoundError`` unless the article exists and the reader may see it."""

        if not await self.repository.exists_visible(article_id, include_hidden):
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))
