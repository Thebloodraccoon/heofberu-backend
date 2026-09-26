"""Article tags service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.articles.cache import ARTICLE_CACHE_NAMESPACES
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

    cache_namespaces = ARTICLE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize with an article tags repository and the article response schema."""

        super().__init__(
            repository=ArticleTagsRepository(db),
            response_schema=ArticleResponse,
        )
