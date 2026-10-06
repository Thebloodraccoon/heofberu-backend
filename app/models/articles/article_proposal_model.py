"""ORM model for a proposed change to someone else's article (a pull request against one of its versions)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import ArticleProposalStatus, ArticleVisibility
from app.models.enums import ArticleProposalStatusType, ArticleVisibilityType
from app.settings.base import Base


class ArticleProposal(Base):
    """
    Full content snapshot a GM who may not edit the article proposes, based on ``base_version``.

    The author or the founder accepts it (it becomes a new ``ArticleRevision`` with ``editor_id = proposer_id``,
    ``reviewer_id = reviewer_id``; its number is kept in ``accepted_version``) or rejects it. Only a proposal
    based on the article's current version can be accepted; the proposer may withdraw it while it is pending.
    ``review_note`` is the reviewer's optional reason for a rejection. Same content fields as ``ArticleRevision``.
    """

    __tablename__ = "article_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    base_version: Mapped[int]
    proposer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)

    title: Mapped[str] = mapped_column(String(200))
    excerpt: Mapped[str | None] = mapped_column(String(500))
    body_markdown: Mapped[str] = mapped_column(Text)
    article_type: Mapped[str] = mapped_column(String(50))
    subtype_id: Mapped[int | None]
    visibility: Mapped[ArticleVisibility] = mapped_column(ArticleVisibilityType)
    change_note: Mapped[str | None] = mapped_column(String(300))

    status: Mapped[ArticleProposalStatus] = mapped_column(
        ArticleProposalStatusType, default=ArticleProposalStatus.PENDING, server_default="PENDING"
    )
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(300))
    accepted_version: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ArticleProposal(id={self.id}, article_id={self.article_id}, status={self.status})>"
