"""Article subtype service: GM-managed dictionary of per-type article subtypes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.features.articles.cache import ARTICLE_CACHE_NAMESPACES
from app.features.articles.subtypes.repository import ArticleSubtypeRepository
from app.features.articles.subtypes.schemas import (
    ArticleSubtypeCreate,
    ArticleSubtypeResponse,
    ArticleSubtypeUpdate,
)
from app.models.articles.article_subtype_model import ArticleSubtype


class ArticleSubtypeService(
    BaseService[ArticleSubtype, ArticleSubtypeCreate, ArticleSubtypeUpdate, ArticleSubtypeResponse, None]
):
    """
    Subtype CRUD. Writes purge the ``articles`` cache: the cached subtype list and article payloads embed
    the subtype name, and a delete nulls ``articles.subtype_id`` (``ON DELETE SET NULL``).
    """

    repository: ArticleSubtypeRepository

    cache_namespaces = ARTICLE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the subtype repository."""

        super().__init__(repository=ArticleSubtypeRepository(db), response_schema=ArticleSubtypeResponse)

    @use_cache()
    async def list_subtypes(self, article_type: str | None) -> list[ArticleSubtypeResponse]:
        """Every subtype, optionally of one ``article_type`` (cached per filter value)."""

        rows = await self.repository.list_subtypes(article_type)
        return [ArticleSubtypeResponse.model_validate(row) for row in rows]
