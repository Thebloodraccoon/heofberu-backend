"""ORM model for a character's participation in a game campaign."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import CampaignCharacterStatus
from app.models.enums import CampaignCharacterStatusType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.campaigns.campaign_model import Campaign
    from app.models.character.character_model import Character


class CampaignCharacter(Base):
    """
    One participation of a character in a campaign (a history row: re-adding after ``REMOVED`` is a new row).

    Added and changed only by the campaign's GM; the player is neither asked nor able to leave. A character is
    in at most one campaign at a time: ``uq_campaign_characters_one_active`` (below) allows a single ``ACTIVE``
    row per character, which is also the row the character access check reads. ``user_id`` copies the
    character's owner so "my campaigns" and the player's read access need no join through ``characters``.
    """

    __tablename__ = "campaign_characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    status: Mapped[CampaignCharacterStatus] = mapped_column(
        CampaignCharacterStatusType, default=CampaignCharacterStatus.ACTIVE, server_default="ACTIVE"
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_campaign_characters_campaign_status", "campaign_id", "status"),
        Index("ix_campaign_characters_character_id", "character_id"),
    )

    campaign: Mapped[Campaign] = relationship(back_populates="characters")
    character: Mapped[Character] = relationship()

    def __repr__(self) -> str:
        return (
            f"<CampaignCharacter(campaign_id={self.campaign_id}, character_id={self.character_id}, "
            f"status={self.status})>"
        )


# A character is in one campaign at a time (status is stored as the member NAME).
Index(
    "uq_campaign_characters_one_active",
    CampaignCharacter.character_id,
    unique=True,
    postgresql_where=text("status = 'ACTIVE'"),
)
