"""ORM model for a background's suggested personality-card entries."""

from sqlalchemy import Column, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.models.enums import BackgroundSuggestionTypeType
from app.settings import settings


class BackgroundSuggestion(settings.Base):  # type: ignore
    """
    One suggested personality-card entry for a background (e.g. Acolyte's
    "I idolize a particular hero of my faith." as a PERSONALITY_TRAIT row).

    Replaces the old ``personality_traits_suggestions``/``ideals_suggestions``/
    ``bonds_suggestions``/``flaws_suggestions`` free-text blobs on
    ``Background`` (one newline-delimited string per field) with one row per
    suggestion, tagged by ``suggestion_type``. Unordered by design — the
    player picks from the set or rolls one at random, not off a numbered list.
    """

    __tablename__ = "background_suggestions"

    id = Column(Integer, primary_key=True)
    background_id = Column(Integer, ForeignKey("backgrounds.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion_type = Column(BackgroundSuggestionTypeType, nullable=False)
    text = Column(Text, nullable=False)

    background = relationship("Background", back_populates="suggestions")

    def __repr__(self):
        return f"<BackgroundSuggestion(background_id={self.background_id}, suggestion_type='{self.suggestion_type}')>"
