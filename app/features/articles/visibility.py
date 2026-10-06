"""Who may see which article: the row filter and the existence check shared by every articles repository."""

from sqlalchemy import select

from app.constants import ArticleStatus, ArticleVisibility
from app.core.base.repository import RepositoryMixin
from app.models.articles.article_model import Article


def visibility_conditions(include_hidden: bool, model=Article) -> list:
    """Row filters hiding unpublished and GM-only articles from non-GM readers (``model``: ``Article`` or an alias)."""

    if include_hidden:
        return []

    return [model.status == ArticleStatus.PUBLISHED, model.visibility == ArticleVisibility.PUBLIC]


class ArticleVisibilityMixin(RepositoryMixin):
    """``exists_visible`` for repositories bound to ``Article`` (needs ``self.db``)."""

    async def exists_visible(self, article_id: int, include_hidden: bool) -> bool:
        """Whether the article exists AND the reader may see it (drafts/GM-only count as missing for non-GMs)."""

        stmt = select(Article.id).where(Article.id == article_id, *visibility_conditions(include_hidden))
        return await self.db.scalar(stmt) is not None
