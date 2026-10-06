"""Article tags service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.articles.base import ArticleScopedService
from app.features.articles.cache import invalidate_articles
from app.features.articles.tags.repository import ArticleTagsRepository
from app.features.shared.tags.mixins import TagsManagerMixin


class ArticleTagService(TagsManagerMixin, ArticleScopedService):
    """Full replacement and id-resolution for an article's tags."""

    repository: ArticleTagsRepository

    def __init__(self, db: AsyncSession):
        """Initialize with an article tags repository and the article response schema."""

        super().__init__(ArticleTagsRepository(db))

    async def _after_tags_set(self, source_id: int) -> None:
        """Drop only this article's cached payload (after the commit), not the whole namespace."""

        await invalidate_articles(self.repository.db, source_id)
