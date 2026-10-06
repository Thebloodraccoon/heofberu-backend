"""ORM model for images uploaded for an article (embedded in its body as markdown)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.articles.article_model import Article


class ArticleImage(Base):
    """
    One image uploaded for an article.

    The row only tracks the Storage object (so it can be listed in the GM editor
    and cleaned up on delete); where and how the image is shown — alt text,
    order, placement — lives in ``body_markdown`` as ``![alt](image_url)``.
    """

    __tablename__ = "article_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)

    image_url: Mapped[str] = mapped_column(String(512), default="")
    #: Random folder in the Storage key (``articles/{article_id}/{storage_key}/{id}.{ext}``): the bucket is
    #: public, so without it an image embedded in a ``:::gm`` block or a draft could be reached by guessing ids.
    storage_key: Mapped[str] = mapped_column(String(36))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    article: Mapped[Article] = relationship(back_populates="images")

    def __repr__(self) -> str:
        return f"<ArticleImage(id={self.id}, article_id={self.article_id})>"
