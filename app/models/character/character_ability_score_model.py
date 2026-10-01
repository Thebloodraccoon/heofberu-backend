"""ORM model for cached, precomputed effective ability scores."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.settings import settings
from app.settings._common import utcnow


class CharacterAbilityScore(settings.Base):  # type: ignore
    """
    Cached, precomputed "effective" ability scores for a character: the base
    score (``Character.strength`` etc.) plus every applicable bonus (race,
    subrace, counted ASI-log increases, granted-feature ASI effects).

    A cache, not a source of truth: the base values on ``Character`` stay
    authoritative. Rows are (re)computed and written only by
    ``CharacterStatsService.refresh`` / ``refresh_many`` — on character
    creation, level-up, ASI/feat/feature grants and GM edits that change a
    source. Read paths (``GET /characters``, ``GET /characters/{id}``) serve
    the row as it is and never recompute; ``GET /characters/{id}/stats``
    always computes fresh. One row per character (``character_id`` is PK and
    FK), so a missing row simply means "never computed yet".
    """

    __tablename__ = "character_ability_scores"

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)

    strength_total = Column(Integer, nullable=False, default=10)
    dexterity_total = Column(Integer, nullable=False, default=10)
    constitution_total = Column(Integer, nullable=False, default=10)
    intelligence_total = Column(Integer, nullable=False, default=10)
    wisdom_total = Column(Integer, nullable=False, default=10)
    charisma_total = Column(Integer, nullable=False, default=10)

    updated_at = Column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
    )

    character = relationship("Character", back_populates="ability_score_cache")

    def __repr__(self):
        return f"<CharacterAbilityScore(character_id={self.character_id})>"
