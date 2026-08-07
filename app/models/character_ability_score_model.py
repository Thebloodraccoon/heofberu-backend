"""ORM model for cached, precomputed effective ability scores."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.settings import settings


class CharacterAbilityScore(settings.Base):  # type: ignore
    """
    Cached, precomputed "effective" ability scores for a character —
    base score (Character.strength etc.) plus every applicable bonus
    (race.ability_bonuses, feat ability_score_increases via
    character_feats).

    This is a cache, not a source of truth: the base values on
    ``Character`` remain authoritative. Rows here are recomputed and
    persisted by ``CharacterStatsService.refresh`` whenever a
    single character is fetched by ID, whenever a character is created,
    whenever a feat is granted/updated/removed, and on character updates
    that touch the base ability scores or ``race_id``. Listing endpoints
    (``GET /characters/``) intentionally read this cache as-is, without
    recomputing, to avoid N recalculations per page — see
    ``CharacterService.get_characters``.

    One row per character (character_id is both PK and FK), so a
    missing row simply means "never computed yet" rather than an error;
    callers should treat a missing row as "recalculate on next read".
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
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    character = relationship("Character", back_populates="ability_score_cache")

    def __repr__(self):
        return f"<CharacterAbilityScore(character_id={self.character_id})>"
