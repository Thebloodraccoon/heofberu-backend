"""Thin bases shared by the article capabilities (CRUD, tags, relations, images) instead of one fat repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.core.base.service import BaseService
from app.features.articles.crud.schemas import ArticleCreate, ArticleResponse, ArticleUpdate
from app.features.articles.visibility import ArticleVisibilityMixin
from app.models.articles.article_model import Article


class ArticleScopedRepository(ArticleVisibilityMixin, BaseRepository[Article]):
    """
    Plain ``Article`` repository: id lookups and the visibility check, nothing capability-specific.

    The capability repositories (relations, images, tags) build on this rather than on
    ``ArticleRepository``, so they don't inherit its tree, listing and search queries. Tags and images
    are only eager-loaded when ``load_tags_and_images`` is set (callers that serialize a full article).
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        load_tags_and_images: bool = False,
        search_fields: list[str] | None = None,
        unique_fields: list[str] | None = None,
    ):
        """Bind to ``Article``; ``search_fields`` defaults to none (not searchable by the generic search)."""

        super().__init__(
            Article,
            db,
            default_load_options=[selectinload(Article.tags), selectinload(Article.images)]
            if load_tags_and_images
            else None,
            search_fields=search_fields or [],
            unique_fields=unique_fields,
        )


class ArticleScopedService(BaseService[Article, ArticleCreate, ArticleUpdate, ArticleResponse, None]):
    """Base of the services that act on one article (``/articles/{id}/tags|relations|images``)."""

    def __init__(self, repository: ArticleScopedRepository):
        """Serialize to ``ArticleResponse`` (only the tags service returns it; the others use the shared helpers)."""

        super().__init__(repository=repository, response_schema=ArticleResponse)
