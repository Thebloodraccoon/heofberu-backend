"""Review-workflow writes: the compare-and-set status move."""

from typing import Any

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ArticleStatus
from app.features.articles.base import ArticleScopedRepository
from app.models.articles.article_model import Article


class ArticleWorkflowRepository(ArticleScopedRepository):
    """Status moves; loads tags and images because the service answers with the full article."""

    def __init__(self, db: AsyncSession):
        """Bind to ``Article`` with tags and images eager-loaded."""

        super().__init__(db, load_tags_and_images=True)

    async def transition_status(
        self,
        article_id: int,
        allowed_from: frozenset[ArticleStatus],
        target: ArticleStatus,
        *,
        reviewer_id: int | None,
        expected_version: int | None = None,
    ) -> bool:
        """
        Move the article to ``target`` only if it is currently in ``allowed_from`` (compare-and-set in one UPDATE).

        Returns whether a row moved, so two concurrent actions can't both pass a stale status check. A first
        publish stamps ``published_at``; ``reviewer_id`` is recorded when given. With ``expected_version`` the move
        also requires the article to still be at that content version (nothing was edited since the reviewer looked).
        """

        values: dict[str, Any] = {"status": target}
        if reviewer_id is not None:
            values["reviewed_by_id"] = reviewer_id
        if target == ArticleStatus.PUBLISHED:
            values["published_at"] = func.coalesce(Article.published_at, func.now())

        conditions = [Article.id == article_id, Article.status.in_(sorted(allowed_from, key=lambda s: s.value))]
        if expected_version is not None:
            conditions.append(Article.version == expected_version)

        result = await self.db.execute(
            update(Article)
            .where(*conditions)
            .values(**values)
            .returning(Article.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None
