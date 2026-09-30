"""Article subtype service: GM-managed dictionary of per-type article subtypes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
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
    Subtype CRUD. Writes purge the ``articles`` cache: cached article payloads embed the subtype name,
    and a delete nulls ``articles.subtype_id`` (``ON DELETE SET NULL``).
    """

    repository: ArticleSubtypeRepository

    cache_namespaces = ARTICLE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the subtype repository."""

        super().__init__(repository=ArticleSubtypeRepository(db), response_schema=ArticleSubtypeResponse)

    async def create(self, create_data: ArticleSubtypeCreate) -> ArticleSubtypeResponse:
        """A new subtype isn't referenced by any cached article payload yet, so skip the namespace flush."""

        item = await self.repository.create(create_data.model_dump())
        return self.response_schema.model_validate(item)

    async def list_subtypes(self, article_type: str | None) -> list[ArticleSubtypeResponse]:
        """Every subtype, optionally of one ``article_type`` (not cached: tiny table)."""

        rows = await self.repository.list_subtypes(article_type)
        return [ArticleSubtypeResponse.model_validate(row) for row in rows]
