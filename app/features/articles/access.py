"""
Who may edit or delete an article: its author or the founder; quests and sessions (``CAMPAIGN_ARTICLE_TYPES``,
the GMs' shared wiki) are edited by any GM, but deleted only by their author or the founder.
"""

from dataclasses import dataclass

from app.constants import CAMPAIGN_ARTICLE_TYPES, UserRole
from app.features.articles.exceptions import ArticleDeleteForbiddenException, ArticleEditForbiddenException


@dataclass(frozen=True)
class ArticleActor:
    """The GM performing a write, reduced to what the edit rules need."""

    id: int
    is_founder: bool

    @classmethod
    def of(cls, user) -> "ArticleActor":
        """Build from an authenticated user (anything with ``id`` and ``role``)."""

        return cls(id=user.id, is_founder=user.role == UserRole.FOUND_FATHER)

    def _is_author(self, author_id: int | None) -> bool:
        return author_id is not None and author_id == self.id

    def can_edit(self, author_id: int | None, article_type: str | None = None) -> bool:
        """
        The founder, the article's author, or any GM for a quest/session, whatever its status (anyone else may
        only propose changes).

        An article without an author (author deleted) is editable by the founder only — unless it is a quest/session.
        """

        return self.is_founder or article_type in CAMPAIGN_ARTICLE_TYPES or self._is_author(author_id)

    def ensure_can_edit(self, article_id: int, author_id: int | None, article_type: str | None = None) -> None:
        """Raise 403 unless ``can_edit``."""

        if not self.can_edit(author_id, article_type):
            raise ArticleEditForbiddenException(article_id)

    def can_delete(self, author_id: int | None, article_type: str) -> bool:
        """The founder any article; a GM only a quest/session they wrote."""

        return self.is_founder or (article_type in CAMPAIGN_ARTICLE_TYPES and self._is_author(author_id))

    def ensure_can_delete(self, article_id: int, author_id: int | None, article_type: str) -> None:
        """Raise 403 unless ``can_delete``."""

        if not self.can_delete(author_id, article_type):
            raise ArticleDeleteForbiddenException(article_id)
