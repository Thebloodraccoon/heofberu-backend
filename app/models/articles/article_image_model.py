"""ORM model for images uploaded for an article (embedded in its body as markdown)."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.settings import settings


class ArticleImage(settings.Base):  # type: ignore
    """
    One image uploaded for an article.

    The row only tracks the Storage object (so it can be listed in the GM editor
    and cleaned up on delete); where and how the image is shown — alt text,
    order, placement — lives in ``body_markdown`` as ``![alt](image_url)``.
    """

    __tablename__ = "article_images"

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)

    image_url = Column(String(512), nullable=False, default="")
    #: Random folder in the Storage key (``articles/{article_id}/{storage_key}/{id}.{ext}``): the bucket is
    #: public, so without it an image embedded in a ``:::gm`` block or a draft could be reached by guessing ids.
    storage_key = Column(String(36), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    article = relationship("Article", back_populates="images")

    def __repr__(self):
        return f"<ArticleImage(id={self.id}, article_id={self.article_id})>"
