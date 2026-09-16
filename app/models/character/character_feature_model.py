"""ORM model for features acquired by a character (with per-character notes)."""

from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.models.enums import GrantSourceType
from app.settings import settings


class CharacterFeature(settings.Base):  # type: ignore
    """
    A feature/trait/feat a character has acquired (from class, subclass,
    race, background, a chosen feat, or a GM manual grant). Kept separate
    from the reference `Feature` table so per-character overrides can be
    recorded without mutating shared reference data.

    ``grant_source`` records where the grant came from (the unified axis that
    replaces ``CharacterFeat.source_type`` and the old implicit
    "``source_type in _AUTO_SOURCE_TYPES``" auto-grant detection):

    - ``AUTO`` — synchronized automatically from ownership of a class /
      subclass / race / subrace / background (progression sync).
    - ``GM`` — manual grant from the GM panel.
    - ``ASI`` — taken instead of an Ability Score Improvement at level-up.

    Choices made for a grant's choice groups are recorded in
    ``character_feature_choices`` (via the ``choices`` relationship); the
    materialized effect rows on the character (skills, saves, armor, weapons,
    granted spells) reference this row through ``source_character_feature_id``.
    """

    __tablename__ = "character_features"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_id = Column(Integer, ForeignKey("features.id", ondelete="CASCADE"), nullable=False, index=True)
    grant_source = Column(GrantSourceType, nullable=False, default="AUTO")

    character = relationship("Character", back_populates="character_features")
    feature = relationship("Feature")
    choices = relationship(
        "CharacterFeatureChoice",
        back_populates="character_feature",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<CharacterFeature(character_id={self.character_id}, feature_id={self.feature_id}, "
            f"grant_source='{self.grant_source}')>"
        )
