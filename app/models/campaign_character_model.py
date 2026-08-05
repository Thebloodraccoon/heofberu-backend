"""ORM model for the campaign <-> character membership association."""

from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.settings import settings


class CampaignCharacter(settings.Base):  # type: ignore
    """
    Association between a campaign and the characters currently in its
    party. Kept as its own model (rather than a plain Table) since it may
    later need per-membership fields (e.g. joined_at, is_active).
    """

    __tablename__ = "campaign_characters"

    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)

    campaign = relationship("Campaign", back_populates="campaign_characters")
    character = relationship("Character")

    def __repr__(self):
        return f"<CampaignCharacter(campaign_id={self.campaign_id}, character_id={self.character_id})>"
