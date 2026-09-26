"""Exceptions for the article images sub-domain."""

from app.core.exceptions import AppError


class ArticleImageNotFoundException(AppError):
    """Raised when an image with the given ID does not exist on this article."""

    status_code = 404

    def __init__(self, article_id: int, image_id: int):
        """Initialize with the article and image ids."""

        self.article_id = article_id
        self.image_id = image_id
        super().__init__(f"Image {image_id} not found for article {article_id}.")
