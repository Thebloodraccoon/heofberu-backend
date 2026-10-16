"""ORM model for who attended a campaign session."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.settings.base import Base


class CampaignSessionAttendance(Base):
    """
    One character that attended one session, marked by the campaign's GM (full replace per session).

    Points at the participation, not the bare character: the archive shows the character as it was in this
    campaign, and the GM can mark a participation that has since ended (``dead``, ``retired``, ``removed``).
    """

    __tablename__ = "campaign_session_attendance"

    session_id: Mapped[int] = mapped_column(ForeignKey("campaign_sessions.id", ondelete="CASCADE"), primary_key=True)
    participation_id: Mapped[int] = mapped_column(
        ForeignKey("campaign_characters.id", ondelete="CASCADE"), primary_key=True
    )

    # "Where did this character play": the PK serves lookups by session, this one by participation.
    __table_args__ = (Index("ix_campaign_session_attendance_participation_id", "participation_id"),)

    def __repr__(self) -> str:
        return f"<CampaignSessionAttendance(session_id={self.session_id}, participation_id={self.participation_id})>"
