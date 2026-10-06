"""Thin bases shared by the article capabilities instead of one fat repository."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.core.base.service import BaseService
from app.features.articles.crud.schemas import ArticleCreate, ArticleResponse, ArticleUpdate
from app.features.articles.visibility import ArticleVisibilityMixin
from app.models.articles.article_model import Article


class ArticleScopedRepository(ArticleVisibilityMixin, BaseRepository[Article]):
    """
    Plain ``Article`` repository: id lookups, the visibility check and the write-rule state, nothing
    capability-specific.

    Every capability repository (crud, tree, listing, workflow, tags, relations, images) builds on this, so none
    inherits another one's queries. Tags and images are eager-loaded only with ``load_tags_and_images`` (repositories
    whose service serializes a full ``ArticleResponse``).
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

    async def get_write_state(self, article_id: int) -> Any:
        """
        The row the write rules need, without tags/images: ``(article_type, subtype_id, published_at, status,
        author_id, version)``; ``None`` if the article doesn't exist.
        """

        result = await self.db.execute(
            select(
                Article.article_type,
                Article.subtype_id,
                Article.published_at,
                Article.status,
                Article.author_id,
                Article.version,
            ).where(Article.id == article_id)
        )
        return result.one_or_none()


class ArticleScopedService(BaseService[Article, ArticleCreate, ArticleUpdate, ArticleResponse]):
    """Base of the services that act on one article and answer with ``ArticleResponse`` (tags, workflow, ...)."""

    def __init__(self, repository: ArticleScopedRepository):
        """Serialize to ``ArticleResponse``; ``_get_response`` needs a repository with ``load_tags_and_images``."""

        super().__init__(repository=repository, response_schema=ArticleResponse)
