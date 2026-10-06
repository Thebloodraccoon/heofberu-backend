"""ORM model for the GM-managed dictionary of article subtypes."""

from __future__ import annotations

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.settings.base import Base


class ArticleSubtype(Base):
    """
    A refinement of one ``article_type`` (location → «таверна», «город», «данж»).

    A subtype belongs to exactly one ``article_type``, fixed at creation; an article may
    only use a subtype of its own type. Names are unique per type, ignoring case.
    """

    __tablename__ = "article_subtypes"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_type: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(50))

    def __repr__(self) -> str:
        return f"<ArticleSubtype(id={self.id}, article_type='{self.article_type}', name='{self.name}')>"


Index("uq_article_subtypes_type_name_lower", ArticleSubtype.article_type, func.lower(ArticleSubtype.name), unique=True)
