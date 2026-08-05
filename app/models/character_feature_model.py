"""ORM model for features acquired by a character (with per-character notes)."""

from sqlalchemy import Column, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.settings import settings


class CharacterFeature(settings.Base):  # type: ignore
    """
    A feature/trait/feat a character has acquired (from class, subclass,
    race, background, or a chosen feat). Kept separate from the reference
    `Feature` table so per-character notes/overrides can be recorded without
    mutating shared reference data.
    """

    __tablename__ = "character_features"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=False, index=True)

    # Player-facing notes/overrides for this specific character, e.g. choices
    # made within the feature (a Fighting Style pick, a chosen skill from a
    # feat, etc). Empty by default.
    notes = Column(Text, nullable=False, default="")

    character = relationship("Character", back_populates="character_features")
    feature = relationship("Feature")

    def __repr__(self):
        return f"<CharacterFeature(character_id={self.character_id}, feature_id={self.feature_id})>"
