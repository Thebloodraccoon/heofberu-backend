"""Who may edit an article: its author, or the founder (the only role that can edit anyone's)."""

from dataclasses import dataclass

from app.constants import UserRole
from app.features.articles.exceptions import ArticleEditForbiddenException


@dataclass(frozen=True)
class ArticleActor:
    """The user performing a write, reduced to what the edit rules need."""

    id: int
    is_founder: bool

    @classmethod
    def of(cls, user) -> "ArticleActor":
        """Build from an authenticated user (anything with ``id`` and ``role``)."""

        return cls(id=user.id, is_founder=user.role == UserRole.FOUND_FATHER)

    def ensure_can_edit(self, article_id: int, author_id: int | None) -> None:
        """
        Pass for the founder or the article's author, whatever its status; raise 403 otherwise.

        An article without an author (author deleted) is editable by the founder only.
        """

        if self.is_founder or (author_id is not None and author_id == self.id):
            return

        raise ArticleEditForbiddenException(article_id)
