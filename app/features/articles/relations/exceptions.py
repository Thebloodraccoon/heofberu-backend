"""Exceptions for the article relations sub-domain."""

from app.core.exceptions import AppError


class ArticleSelfRelationException(AppError):
    """Raised when a relation would link an article to itself."""

    status_code = 400

    def __init__(self, article_id: int):
        """Initialize with the article id."""

        self.article_id = article_id
        super().__init__(f"Article {article_id} cannot be related to itself.")


class ArticleRelationNotFoundException(AppError):
    """Raised when a relation with the given ID does not exist on this article (either direction)."""

    status_code = 404

    def __init__(self, article_id: int, relation_id: int):
        """Initialize with the article and relation ids."""

        self.article_id = article_id
        self.relation_id = relation_id
        super().__init__(f"Relation {relation_id} not found for article {article_id}.")
