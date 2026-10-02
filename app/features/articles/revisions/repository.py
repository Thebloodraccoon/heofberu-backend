"""Read queries over ``article_revisions`` (writes live in ``ArticleRepository.record_revision``)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.articles.article_model import Article
from app.models.articles.article_revision_model import ArticleRevision


class ArticleRevisionRepository:
    """Newest-first history of one article; every read is for GMs, so no visibility filtering."""

    def __init__(self, db: AsyncSession):
        """Bind to a session."""

        self.db = db

    async def article_exists(self, article_id: int) -> bool:
        """Whether the article exists (to tell an empty history from a missing article)."""

        return await self.db.scalar(select(Article.id).where(Article.id == article_id)) is not None

    async def list_for_article(self, article_id: int, *, skip: int, limit: int) -> tuple[list[ArticleRevision], int]:
        """Return one page of the history, newest version first, and its total size."""

        total = await self.db.scalar(
            select(func.count()).select_from(ArticleRevision).where(ArticleRevision.article_id == article_id)
        )
        result = await self.db.execute(
            select(ArticleRevision)
            .where(ArticleRevision.article_id == article_id)
            .order_by(ArticleRevision.version.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total or 0

    async def get(self, article_id: int, version: int) -> ArticleRevision | None:
        """Return one snapshot, or ``None``."""

        return await self.db.scalar(
            select(ArticleRevision).where(ArticleRevision.article_id == article_id, ArticleRevision.version == version)
        )
