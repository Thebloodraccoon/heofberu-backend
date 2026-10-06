"""ORM model for the version history of an article (one immutable snapshot per saved change)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import ArticleVisibility
from app.models.enums import ArticleVisibilityType
from app.settings.base import Base


class ArticleRevision(Base):
    """
    Snapshot of an article's *content* right after a save: ``(article_id, version)`` is unique and ``version``
    mirrors ``articles.version`` at that moment.

    Only content is versioned (title, excerpt, body, type, subtype, visibility). Structure (``parent_id``/``slug``),
    workflow (``status``) and tags/images/relations are not, so restoring a revision never moves the article in the
    tree or changes its review state. ``subtype_id`` has no FK on purpose: a snapshot must outlive a deleted subtype.
    """

    __tablename__ = "article_revisions"
    __table_args__ = (UniqueConstraint("article_id", "version", name="uq_article_revisions_article_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    version: Mapped[int]

    title: Mapped[str] = mapped_column(String(200))
    excerpt: Mapped[str | None] = mapped_column(String(500))
    body_markdown: Mapped[str] = mapped_column(Text)
    article_type: Mapped[str] = mapped_column(String(50))
    subtype_id: Mapped[int | None]
    visibility: Mapped[ArticleVisibility] = mapped_column(ArticleVisibilityType)

    #: Like git's author/committer: who wrote the change and who approved it. A direct edit by the author or the
    #: founder is self-reviewed (both the same user); an accepted proposal has proposer -> editor, acceptor -> reviewer.
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    #: ``revisions.hashing.revision_hash`` of this snapshot, chained to the previous version's hash.
    content_hash: Mapped[str] = mapped_column(String(64))
    change_note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ArticleRevision(article_id={self.article_id}, version={self.version})>"
