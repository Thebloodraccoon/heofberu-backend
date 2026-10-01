"""ORM model for features acquired by a character (with per-character notes)."""

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
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
    ``character_feature_choices`` (via the ``choices`` relationship). What
    the grant gives (skills, saves, armor, weapons, spells) is not stored:
    it is computed on read from the feature's effect tree plus those picks
    (``app.features.characters.grants.effects``).
    """

    __tablename__ = "character_features"
    # One grant per (character, feature): repositories read the pair with ``scalar_one_or_none()``.
    __table_args__ = (UniqueConstraint("character_id", "feature_id", name="uq_character_features_character_feature"),)

    id = Column(Integer, primary_key=True)
    # No own index: the unique (character_id, feature_id) already leads with ``character_id``.
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
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
