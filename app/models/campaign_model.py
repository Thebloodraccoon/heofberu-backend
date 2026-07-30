from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.settings import settings


class Campaign(settings.Base):  # type: ignore
    """A campaign run by a GM, grouping player characters into a party."""

    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True)
    gm_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    gm = relationship("User")
    characters = relationship(
        "Character",
        secondary="campaign_characters",
        viewonly=True,
    )
    campaign_characters = relationship(
        "CampaignCharacter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Campaign(id={self.id}, name='{self.name}', gm_id={self.gm_id})>"
