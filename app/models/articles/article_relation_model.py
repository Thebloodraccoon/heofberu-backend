"""ORM model for typed directed relationships between two articles."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.constants import ArticleVisibility
from app.models.enums import ArticleVisibilityType
from app.settings import settings


class ArticleRelation(settings.Base):  # type: ignore
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

    id = Column(Integer, primary_key=True)
    from_article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    to_article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)

    relation_type = Column(String(50), nullable=False, index=True)
    note = Column(String(300), nullable=True)

    # A GM_ONLY relation is hidden from non-GMs even when both articles are public (a secret allegiance).
    visibility = Column(
        ArticleVisibilityType, nullable=False, default=ArticleVisibility.PUBLIC, server_default="PUBLIC"
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    from_article = relationship("Article", foreign_keys=[from_article_id])
    to_article = relationship("Article", foreign_keys=[to_article_id])

    def __repr__(self):
        return f"<ArticleRelation(id={self.id}, {self.from_article_id}-[{self.relation_type}]->{self.to_article_id})>"
