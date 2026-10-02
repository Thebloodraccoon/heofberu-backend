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


class ArticleTreeTooDeepException(AppError):
    """Raised (400) when placing an article would push its subtree past the supported nesting depth."""

    status_code = 400

    def __init__(self, article_id: int, max_depth: int):
        """Initialize with the article being placed and the maximum tree depth."""

        self.article_id = article_id
        self.max_depth = max_depth
        super().__init__(
            f"Article {article_id} cannot be placed there: the tree may be at most {max_depth} levels deep."
        )


class ArticleStatusTransitionException(AppError):
    """Raised (409) when a review-workflow action isn't allowed from the article's current status."""

    status_code = 409

    def __init__(self, article_id: int, action: str, current_status: str):
        """Initialize with the article, the rejected action and the status it was attempted from."""

        self.article_id = article_id
        self.action = action
        self.current_status = current_status
        super().__init__(f"Cannot {action} article {article_id}: it is {current_status}.")


class ArticleVersionMismatchException(AppError):
    """Raised (409) when an article is published at a version other than the current one (it was edited meanwhile)."""

    status_code = 409

    def __init__(self, article_id: int, expected: int, current: int):
        """Initialize with the article, the version the reviewer confirmed and its actual current version."""

        self.article_id = article_id
        self.expected = expected
        self.current = current
        super().__init__(
            f"Article {article_id} is at version {current}, not {expected}: it was edited after you reviewed it. "
            f"Review the changes (GET /articles/{article_id}/revisions/{current}/diff) and publish again."
        )


class ArticleEditForbiddenException(AppError):
    """Raised (403) when a GM edits an article they didn't write: they may only propose changes to it."""

    status_code = 403

    def __init__(self, article_id: int):
        """Initialize with the article the caller may not edit."""

        self.article_id = article_id
        super().__init__(f"You can only edit your own articles; article {article_id} belongs to someone else.")


class ArticleSubtypeTypeMismatchException(AppError):
    """Raised (400) when an article would use a subtype of a different ``article_type``."""

    status_code = 400

    def __init__(self, subtype_id: int, subtype_type: str, article_type: str):
        """Initialize with the subtype, the type it belongs to and the article's type."""

        self.subtype_id = subtype_id
        super().__init__(
            f"Subtype {subtype_id} belongs to article_type '{subtype_type}', not '{article_type}'. "
            "Change or clear subtype_id together with article_type."
        )
