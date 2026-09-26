"""Exceptions shared across the articles domain."""

from app.core.exceptions import AppError


class ArticleParentCycleException(AppError):
    """Raised when an article would become its own ancestor (parent is itself or one of its descendants)."""

    status_code = 400

    def __init__(self, article_id: int, parent_id: int):
        """Initialize with the article and the rejected parent ids."""

        self.article_id = article_id
        self.parent_id = parent_id
        super().__init__(f"Article {parent_id} cannot be the parent of article {article_id}: it would create a cycle.")
