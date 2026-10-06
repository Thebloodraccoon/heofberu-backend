"""Association table linking articles to the shared Tag dictionary."""

from sqlalchemy import Column, ForeignKey, Index, Integer, Table

from app.settings.base import Base

# articles <-> tags (shared Tag dictionary; orthogonal to article_type and to
# the parent/path hierarchy and to ArticleRelation)
article_tags = Table(
    "article_tags",
    Base.metadata,
    Column("article_id", Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True),
    # The composite PK is (article_id, tag_id) — a lone `WHERE tag_id = ...`
    # can't use it, hence this index.
    Index("ix_article_tags_tag_id", "tag_id"),
)
