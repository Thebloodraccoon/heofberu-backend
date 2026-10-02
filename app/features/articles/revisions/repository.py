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

    async def list_for_article(
        self, article_id: int, *, skip: int, limit: int, before_version: int | None = None, with_total: bool = True
    ) -> tuple[list[ArticleRevision], int | None]:
        """
        Return one page of the history, newest version first, and its total size (``None`` without ``with_total``);
        ``before_version`` is the keyset position (only older versions).
        """

        total = None
        if with_total:
            total = await self.db.scalar(
                select(func.count()).select_from(ArticleRevision).where(ArticleRevision.article_id == article_id)
            )
        conditions = [ArticleRevision.article_id == article_id]
        if before_version is not None:
            conditions.append(ArticleRevision.version < before_version)

        result = await self.db.execute(
            select(ArticleRevision)
            .where(*conditions)
            .order_by(ArticleRevision.version.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def get(self, article_id: int, version: int) -> ArticleRevision | None:
        """Return one snapshot, or ``None``."""

        return await self.db.scalar(
            select(ArticleRevision).where(ArticleRevision.article_id == article_id, ArticleRevision.version == version)
        )
