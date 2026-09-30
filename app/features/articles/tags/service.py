"""Article tags service: full replacement and id resolution."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.articles.cache import invalidate_article
from app.features.articles.crud.schemas import ArticleCreate, ArticleResponse, ArticleUpdate
from app.features.articles.tags.repository import ArticleTagsRepository
from app.features.shared.tags.mixins import TagsManagerMixin
from app.models.articles.article_model import Article


class ArticleTagService(
    TagsManagerMixin,
    BaseService[Article, ArticleCreate, ArticleUpdate, ArticleResponse, None],
):
    """Full replacement and id-resolution for an article's tags."""

    repository: ArticleTagsRepository

    def __init__(self, db: AsyncSession):
        """Initialize with an article tags repository and the article response schema."""

        super().__init__(
            repository=ArticleTagsRepository(db),
            response_schema=ArticleResponse,
        )

    async def set_tags(self, source_id: int, data: Any) -> ArticleResponse:
        """Like ``TagsManagerMixin.set_tags``, but point-invalidates instead of flushing the whole namespace."""

        await self._exists_or_404(source_id)
        tags = await self._resolve_tags(data.tag_ids)

        await self.repository.set_tags(source_id, tags)
        await invalidate_article(source_id)

        return await self._get_response(source_id)
