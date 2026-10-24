"""ORM model for a game campaign: one GM's table (characters, sessions, notes, reviews)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import CampaignStatus
from app.models.enums import CampaignStatusType
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.campaigns.campaign_character_model import CampaignCharacter
    from app.models.campaigns.public_campaign_model import PublicCampaign
    from app.models.user_model import User


class Campaign(Base):
    """
    A game campaign, owned by exactly one GM.

    Deleting the GM's account keeps the campaign (``owner_id`` becomes ``NULL``): its players keep reading it and the
    founder keeps managing it (e.g. releasing its characters); there is no ownership transfer.

    Seen in full by its owner and the founder; players whose character takes part in it (any status but
    ``REMOVED``) see the player view (``:::gm`` blocks stripped, unpublished chronicles closed). Other GMs don't
    see it at all. ``public_campaign_id`` optionally links it to the public campaign (preset) it was made from;
    the link feeds the public showcase and reviews.
    """

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    public_campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("public_campaigns.id", ondelete="SET NULL"), index=True
    )

    title: Mapped[str] = mapped_column(String(200))
    description_markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[CampaignStatus] = mapped_column(
        CampaignStatusType, default=CampaignStatus.PLANNING, server_default="PLANNING", index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id], lazy="joined")
    public_campaign: Mapped[PublicCampaign | None] = relationship(back_populates="campaigns")
    characters: Mapped[list[CampaignCharacter]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Campaign(id={self.id}, owner_id={self.owner_id}, status={self.status})>"
