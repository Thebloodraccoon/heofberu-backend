"""ORM model for a campaign session (one game night): its date, status and chronicle."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import CampaignSessionStatus
from app.models.enums import CampaignSessionStatusType
from app.settings.base import Base


class CampaignSession(Base):
    """
    A session of a campaign: when it is (or was) played, who attended, and the GM's chronicle.

    Players see every session of their campaign (number, title, status, ``scheduled_at``, attendance), which makes
    the session list the table's schedule and archive. The chronicle is a separate matter: players read it only
    once ``published_at`` is set, and without ``:::gm`` blocks (the same syntax as articles).
    """

    __tablename__ = "campaign_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[CampaignSessionStatus] = mapped_column(
        CampaignSessionStatusType, default=CampaignSessionStatus.PLANNED, server_default="PLANNED"
    )
    # When the session is planned for; the GM corrects it to the real time once played.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chronicle_markdown: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "number", name="uq_campaign_sessions_number"),
        # The schedule: sessions of the caller's campaigns in a time window.
        Index("ix_campaign_sessions_campaign_scheduled", "campaign_id", "scheduled_at"),
    )

    def __repr__(self) -> str:
        return f"<CampaignSession(id={self.id}, campaign_id={self.campaign_id}, number={self.number})>"
