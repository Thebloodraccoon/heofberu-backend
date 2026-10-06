"""ORM model for typed directed relationships between two articles."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import ArticleVisibility
from app.models.enums import ArticleVisibilityType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.articles.article_model import Article


class ArticleRelation(Base):
    """
    A typed directed relationship between two articles is a graph of everything
    that doesn't fit into the ``Article.parent_id`` hierarchy (membership,
    kinship, feud, mentions). ``relation_type`` is an open
    list (see ``RELATION_TYPES``), not a Postgres ENUM.
    """

    __tablename__ = "article_relations"
    __table_args__ = (
        UniqueConstraint("from_article_id", "to_article_id", "relation_type", name="uq_article_relation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # No own index: ``uq_article_relation`` (from, to, type) already leads with ``from_article_id``.
    from_article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    to_article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)

    relation_type: Mapped[str] = mapped_column(String(50), index=True)
    note: Mapped[str | None] = mapped_column(String(300))

    # A GM_ONLY relation is hidden from non-GMs even when both articles are public (a secret allegiance).
    visibility: Mapped[ArticleVisibility] = mapped_column(
        ArticleVisibilityType, default=ArticleVisibility.PUBLIC, server_default="PUBLIC"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    from_article: Mapped[Article] = relationship(foreign_keys=[from_article_id])
    to_article: Mapped[Article] = relationship(foreign_keys=[to_article_id])

    def __repr__(self) -> str:
        return f"<ArticleRelation(id={self.id}, {self.from_article_id}-[{self.relation_type}]->{self.to_article_id})>"
