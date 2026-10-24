"""ORM models for player reviews: of a whole campaign (public) and of one session (for the GM)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.user_model import User


class CampaignReview(Base):
    """
    A player's review of a whole campaign: one per player and campaign, editable by its author.

    Public: shown inside the campaign and on its linked public campaign. The GM can't remove it; the founder can
    hide it (``hidden_at``), which drops it from every listing.
    """

    __tablename__ = "campaign_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("campaign_id", "author_id", name="uq_campaign_reviews_author"),)

    author: Mapped[User] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<CampaignReview(id={self.id}, campaign_id={self.campaign_id}, author_id={self.author_id})>"


class SessionReview(Base):
    """
    A player's review of one session: one per player and session.

    The GM (and the founder) always see it; the rest of the table only when the author turns
    ``visible_to_table`` on. The founder can hide it (``hidden_at``), which drops it from every listing.
    """

    __tablename__ = "session_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("campaign_sessions.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    visible_to_table: Mapped[bool] = mapped_column(default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("session_id", "author_id", name="uq_session_reviews_author"),)

    author: Mapped[User] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<SessionReview(id={self.id}, session_id={self.session_id}, author_id={self.author_id})>"
