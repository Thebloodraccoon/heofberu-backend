"""ORM model for a GM's private campaign notes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.settings.base import Base


class CampaignNote(Base):
    """A private note of the campaign's GM (plot lines, NPCs, prep). Only the owner and the founder see it."""

    __tablename__ = "campaign_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    body_markdown: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_campaign_notes_campaign_id", "campaign_id"),)

    def __repr__(self) -> str:
        return f"<CampaignNote(id={self.id}, campaign_id={self.campaign_id})>"
